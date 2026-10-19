"""Integration checks for the static app, using Chromium and a Web Serial peer."""
from pathlib import Path
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
import os
import time
import unittest

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BACKGROUND, LAND, SELECTED = '#ffd54f', '#ff8a3d', '#8b4513'
HK, TOKYO, LONDON = 2290, 2101, 1886
USB_MOCK = r'''(() => {
 window.__usbCommands=[];
 let input;
 const port={async open(){
  this.readable=new ReadableStream({start(c){input=c;}});
  this.writable=new WritableStream({write(bytes){
   const cmd=JSON.parse(new TextDecoder().decode(bytes));window.__usbCommands.push(cmd);
   const reply={v:1,device:'MongBB',id:cmd.id,ok:true};
   if(cmd.op==='hello')Object.assign(reply,{protocol:'mongbb-usb/1',firmware:'1.1.0',width:64,height:64,outputEnabled:true,brightnessCap:32,hasScene:true});
   input.enqueue(new TextEncoder().encode(JSON.stringify(reply)+String.fromCharCode(10)));
  }});
 },async close(){}};
 Object.defineProperty(navigator,'serial',{configurable:true,value:{requestPort:async()=>port}});
})();'''


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class CityColorsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
        Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'),
            headless=True, args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width':1440,'height':1100}, reduced_motion='reduce', accept_downloads=True)
        self.context.add_init_script(USB_MOCK)
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.errors = []
        self.page.on('pageerror', lambda error:self.errors.append(str(error)))
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}/', wait_until='networkidle')

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def state(self):
        return self.page.evaluate('window.__MONG_DIAGNOSTICS()')

    def download_json(self, label):
        with self.page.expect_download() as event:
            self.page.get_by_role('button', name=label, exact=True).click()
        return json.loads(Path(event.value.path()).read_text())

    def upload_json(self, data, city=False):
        field = self.page.locator('#city-map input[type=file]') if city else self.page.locator('.export-panel input[type=file]')
        field.set_input_files({'name':'test-settings.json','mimeType':'application/json','buffer':json.dumps(data).encode()})

    def wait_for_commit(self, start=0):
        deadline = time.monotonic() + 15
        while True:
            commands = self.page.evaluate('window.__usbCommands')
            if len(commands)>start and commands[-1]['op']=='commit':
                expect(self.page.locator('.device-status')).to_contain_text('ESP32 已確認接收')
                return commands[start:]
            self.assertLess(time.monotonic(), deadline, 'No completed USB upload')
            self.page.wait_for_timeout(100)

    def test_region_controls_change_preview_and_transmitted_pixels(self):
        # Catches disconnected color controls, lost backgrounds, and brightness resets.
        for label, color in [('背景顏色',BACKGROUND),('未選取地圖顏色',LAND),('已選取地圖顏色',SELECTED)]:
            expect(self.page.get_by_label(label, exact=True)).to_have_value(color)
        self.page.get_by_role('button',name='載入城市地圖模板',exact=True).click()
        before = self.state()
        self.assertEqual(before['lit'],4096)
        self.assertEqual(before['state']['matrixBrightness'], .1)
        self.assertEqual(before['state']['pixelColors'][0], BACKGROUND)
        for point in (HK,TOKYO,LONDON):
            self.assertNotEqual(before['state']['pixelColors'][point], LAND)
        self.page.get_by_role('slider',name='Matrix 相對亮度',exact=True).press('ArrowRight')
        self.assertAlmostEqual(self.state()['state']['matrixBrightness'], .11)
        self.page.get_by_label('背景顏色',exact=True).fill('#ffee00')
        after = self.state()
        changed={i for i,(a,b) in enumerate(zip(before['state']['pixelColors'],after['state']['pixelColors'])) if a!=b}
        self.assertEqual(len(changed),3512)
        self.assertEqual(after['state']['pixelColors'][HK],before['state']['pixelColors'][HK])
        self.assertNotEqual(after['source'][:3],before['source'][:3])
        self.page.get_by_label('香港開燈',exact=True).uncheck()
        unselected=self.state()
        self.assertEqual(unselected['state']['pixelColors'][HK],LAND)
        self.assertEqual(unselected['state']['pixelColors'][0],'#ffee00')
        self.assertAlmostEqual(unselected['state']['matrixBrightness'],.11)
        self.page.get_by_label('香港開燈',exact=True).check()
        self.page.get_by_label('未選取地圖顏色',exact=True).fill('#0088ff')
        self.page.get_by_label('已選取地圖顏色',exact=True).fill('#aa33cc')
        final=self.state()
        self.page.get_by_role('button',name='連接 ESP32',exact=True).click()
        self.page.get_by_role('button',name='傳送目前圖案',exact=True).click()
        commands=self.wait_for_commit()
        self.assertAlmostEqual(next(c['config']['brightness'] for c in commands if c['op']=='begin'), .11)
        rows={c['y']:c for c in commands if c['op']=='row'}
        self.assertEqual(len(rows),64)
        for y,row in rows.items():
            self.assertEqual(row['mask'],'1'*64)
            self.assertEqual(row['colors'],''.join(c[1:] for c in final['state']['pixelColors'][y*64:y*64+64]))
        canvas_colors=self.page.locator('.city-canvas').evaluate('e=>[0,2290,2101,1886].map(i=>Array.from(e.getContext("2d").getImageData(i%64*12+6,Math.floor(i/64)*12+6,1,1).data).slice(0,3))')
        expected=[[int(final['state']['pixelColors'][i][k:k+2],16) for k in (1,3,5)] for i in (0,HK,TOKYO,LONDON)]
        self.assertEqual(canvas_colors,expected)
        start=len(self.page.evaluate('window.__usbCommands'))
        self.page.get_by_label('即時同步至 ESP32',exact=True).check()
        self.page.get_by_label('背景顏色',exact=True).fill('#11ee66')
        live=self.wait_for_commit(start)
        self.assertTrue(any(c['op']=='row' and c['y']==0 and c['colors']=='11ee66'*64 for c in live))
        if capture_dir := os.environ.get('MONG_TEST_CAPTURE_DIR'):
            capture = Path(capture_dir)
            capture.mkdir(parents=True,exist_ok=True)
            (capture/'commands.json').write_text(json.dumps(self.page.evaluate('window.__usbCommands')))
            frame=self.state()
            (capture/'expected.json').write_text(json.dumps({key:frame[key] for key in ('state','mask','source')}))

    def test_palette_and_city_selection_survive_both_json_round_trips(self):
        self.page.get_by_label('背景顏色',exact=True).fill('#fce155')
        self.page.get_by_label('未選取地圖顏色',exact=True).fill('#ef7d22')
        self.page.get_by_label('已選取地圖顏色',exact=True).fill('#713a18')
        self.page.get_by_label('東京開燈',exact=True).uncheck()
        city=self.download_json('↓ 城市設定 JSON')
        whole=self.download_json('↓ 設定 JSON')
        expected=self.state()['state']['pixelColors']
        self.page.get_by_label('背景顏色',exact=True).fill('#000000')
        self.upload_json(city,city=True)
        expect(self.page.get_by_label('背景顏色',exact=True)).to_have_value('#fce155')
        expect(self.page.get_by_label('東京開燈',exact=True)).not_to_be_checked()
        self.assertEqual(self.state()['state']['pixelColors'],expected)
        self.page.reload(wait_until='networkidle')
        self.upload_json(whole)
        expect(self.page.get_by_text('設定及 4,096 個地圖像素已還原。',exact=True)).to_be_visible()
        expect(self.page.get_by_label('背景顏色',exact=True)).to_have_value('#fce155')
        expect(self.page.get_by_label('東京開燈',exact=True)).not_to_be_checked()
        self.assertEqual(self.state()['state']['pixelColors'],expected)
        self.page.get_by_label('東京開燈',exact=True).check()
        self.assertEqual(self.state()['state']['pixelColors'][0],'#fce155')

    def test_legacy_city_colors_and_black_background(self):
        legacy=self.download_json('↓ 城市設定 JSON')
        legacy['schemaVersion']=1
        legacy['base']=32
        legacy.pop('palette')
        legacy['cities'][0].update(color='#00ff00',brightness=255)
        self.upload_json(legacy,city=True)
        expect(self.page.get_by_label('使用三區配色',exact=True)).not_to_be_checked()
        expect(self.page.get_by_label('背景顏色',exact=True)).to_be_disabled()
        state=self.state()
        self.assertEqual(state['mask'][0],0)
        self.assertEqual(state['state']['pixelColors'][HK],'#00ff00')
        expect(self.page.get_by_label('所選城市顏色',exact=True)).to_have_value('#00ff00')
        self.page.get_by_label('使用三區配色',exact=True).check()
        self.page.get_by_label('背景顏色',exact=True).fill('#000000')
        state=self.state()
        self.assertEqual(state['lit'],584)
        self.assertEqual(state['source'][:3],[0,0,0])
        self.assertEqual(state['mask'][0],0)
        # All city locations remain map-colored even when outside the land mask.
        land=''.join((ROOT/'downloads/world-map-64x64.txt').read_text().split())
        off_land=next(c for c in legacy['cities'] if not c['on'] and any(land[p]=='0' for p in c['pixels']))
        for point in off_land['pixels']:
            self.assertEqual(state['mask'][point],1)

    def test_bad_palette_import_is_atomic(self):
        self.page.get_by_role('button',name='載入城市地圖模板',exact=True).click()
        expected=self.state()
        city=self.download_json('↓ 城市設定 JSON')
        city['palette']['selected']='#nothex'
        city['cities'][0]['on']=False
        self.upload_json(city,city=True)
        expect(self.page.locator('.city-message')).to_contain_text('三區配色格式無效')
        self.assertEqual(self.state()['state'],expected['state'])
        expect(self.page.get_by_label('香港開燈',exact=True)).to_be_checked()
        whole=self.download_json('↓ 設定 JSON')
        whole['cityMap']['palette']['background']='yellow'
        whole['settings']['matrixBrightness']=.7
        self.upload_json(whole)
        expect(self.page.get_by_text('匯入失敗：三區配色格式無效；請使用有效的六位色碼。',exact=True)).to_be_visible()
        self.assertEqual(self.state()['state'],expected['state'])
        expect(self.page.get_by_label('背景顏色',exact=True)).to_have_value(BACKGROUND)


if __name__=='__main__':
    unittest.main()
