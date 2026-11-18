// 使用调试平台真实 CSS / HarmonyOS 字体验证可见字底，而不是仅比较文字框。
// node s_center_glyph_alignment.mjs <宽> <高> <输出目录> <浏览器路径> [缩放]
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildSync } from 'esbuild';
import { chromium } from 'playwright-core';

const [widthArg, heightArg, outputArg, browserPath, scaleArg = '1'] = process.argv.slice(2);
const width = Number(widthArg), height = Number(heightArg), scale = Number(scaleArg);
assert(width > 0 && height > 0 && scale > 0 && outputArg && browserPath,
  '必须显式指定卡片宽高、输出目录、浏览器；缩放可选');
const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const debugRoot = path.join(repository, 'debug_tools');
const output = path.resolve(outputArg);
mkdirSync(output, { recursive: true });
const python = String.raw`
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path('widget_service/cloud').resolve()))
from services.compact_dsl_a2ui_converter import convert_compact_dsl_to_a2ui
samples=[]
for label, value, unit, subtitle in [
    ('学校秋季运动会开幕倒计时',58,'天','距12月26日'),
    ('运动会\n倒计时',102,'天',None),
    ('耳机电量',85,'%','左耳'),
    ('电量变化',-8.5,'%',None),
]:
    props={
        'label':label,
        'value':value,'unit':unit,'fontColor':'#FFFFFFFF',
    }
    if subtitle is not None:
        props['secondaryInfo']=subtitle
    rows=[
        ['root','Layout',{'layout':'S-center','backgroundColor':'#FF9C4E22'},['display']],
        ['display','DataDisplay',props],
    ]
    source='\n'.join(json.dumps(row,ensure_ascii=False) for row in rows)
    samples.append(convert_compact_dsl_to_a2ui(source,size='2x2'))
print(json.dumps(samples,ensure_ascii=False))
`;
const sources = JSON.parse(execFileSync('uv', ['run', '--no-sync', 'python', '-c', python], {
  cwd: repository, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
}));
let css = readFileSync(path.join(debugRoot, 'card_renderer/frontend/src/styles.css'), 'utf8');
css = css.replace(/url\("\/fonts\/harmonyos\/([^"]+)"\)/g, (_, name) =>
  'url("data:font/ttf;base64,' + readFileSync(path.join(debugRoot,
    'card_renderer/assets/fonts/harmonyos', name)).toString('base64') + '")');
const app = `import React from 'react';import {createRoot} from 'react-dom/client';
import {UIGraph} from './card_renderer/runtime/graph/src/graph.ts';
import {JsonlStreamParser} from './card_renderer/runtime/parser/src/parser.ts';
import {renderTree,defaultRegistry} from './card_renderer/runtime/renderer/src/index.ts';
window.React=React;
const sources=${JSON.stringify(sources)};
for(let i=0;i<sources.length;i++){
 const graph=new UIGraph();
 const parser=new JsonlStreamParser({onMessage:c=>graph.applyCommand(c),onParseError:(_,e)=>{throw e;}});
 parser.push(sources[i]);parser.end();
 createRoot(document.getElementById('card'+i)).render(renderTree(graph,defaultRegistry));
}`;
const bundle = buildSync({ stdin: { contents: app, resolveDir: debugRoot, loader: 'tsx' },
  bundle: true, write: false, format: 'iife', jsx: 'transform' }).outputFiles[0].text;
const browser = await chromium.launch({ executablePath: browserPath, headless: true });
try {
  const page = await browser.newPage({ viewport: {
    width: Math.ceil((width * scale + 20) * sources.length + 20),
    height: Math.ceil(height * scale + 40),
  }, deviceScaleFactor: 2 });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setContent('<meta charset="utf-8"><style>' + css + '</style>' +
    '<style>body.card-renderer{display:flex;height:auto;margin:20px;gap:20px}' +
    `.slot{width:${width * scale}px;height:${height * scale}px;flex-shrink:0}` +
    `.card{width:${width}px;height:${height}px;transform:scale(${scale});transform-origin:top left}` +
    '</style><body class="card-renderer">' + sources.map((_, i) =>
      '<section class="slot"><div class="card" id="card'+i+'"></div></section>').join(''));
  await page.addScriptTag({ content: bundle });
  await page.waitForSelector('#card3 [data-node-id="display_unit"]');
  await page.evaluate(async () => {
    await document.fonts.load('700 46px "HarmonyOS Sans SC"');
    await document.fonts.load('500 16px "HarmonyOS Sans SC"');
    await document.fonts.load('500 12px "HarmonyOS Sans SC"');
    await document.fonts.ready;
  });
  const png = await page.screenshot({ path: path.join(output, 'preview.png') });
  const unclipped = await page.screenshot({ style: [
    '[data-node-id="display_value"], [data-node-id="display_unit"],',
    '[data-node-id="display_secondary"] { overflow: visible !important; }',
  ].join('\n') });
  const evidence = await page.evaluate(async ({dataUrl, unclippedUrl}) => {
    const image = new Image(); image.src = dataUrl; await image.decode();
    const unclippedImage = new Image(); unclippedImage.src = unclippedUrl; await unclippedImage.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.width; canvas.height = image.height;
    const ctx = canvas.getContext('2d');ctx.drawImage(image,0,0);
    const ratio = image.width / innerWidth;
    function bottom(element) {
      const rect=element.getBoundingClientRect();
      const x0=Math.floor(rect.x*ratio),y0=Math.floor(rect.y*ratio);
      const width=Math.ceil(rect.right*ratio)-x0,height=Math.ceil(rect.bottom*ratio)-y0;
      const pixels=ctx.getImageData(x0,y0,width,height).data;
      let last=-1;
      for(let y=0;y<height;y++)for(let x=0;x<width;x++){
        const i=(y*width+x)*4;
        if(Math.min(pixels[i],pixels[i+1],pixels[i+2])>225)last=y;
      }
      if(last<0)throw Error('没有找到前景字形像素');
      return (y0+last)/ratio;
    }
    return Array.from(document.querySelectorAll('.card')).map(card=>{
      const number=card.querySelector('[data-node-id="display_value"]');
      const unit=card.querySelector('[data-node-id="display_unit"]');
      const numberBottom=bottom(number),unitBottom=bottom(unit);
      const rect = id => card.querySelector('[data-node-id="'+id+'"]').getBoundingClientRect();
      const display=rect('display'),title=rect('display_title_area');
      const area=rect('display_numeric_area'),row=rect('display_value_row');
      const cardBox=card.getBoundingClientRect();
      const label=rect('display_label');
      const subtitle=card.querySelector('[data-node-id="display_secondary"]');
      const subtitleBox=subtitle?.getBoundingClientRect();
      const numberBox=number.getBoundingClientRect(),unitBox=unit.getBoundingClientRect();
      const geometry={displayHeight:display.height,titleHeight:title.height,labelHeight:label.height,
        labelCenterOffset:(label.top+label.bottom-title.top-title.bottom)/2,
        labelWeight:getComputedStyle(card.querySelector('[data-node-id="display_label"]')).fontWeight,
        subtitleHeight:subtitleBox?.height,subtitleGap:subtitleBox && subtitleBox.top-label.bottom,
        subtitleFont:subtitle && getComputedStyle(subtitle).fontSize,
        titleTop:title.top-cardBox.top,gap:area.top-title.bottom,
        numericAreaHeight:area.height,rowHeight:row.height,
        rowCenterOffset:(row.top+row.bottom-area.top-area.bottom)/2,
        valueHeight:numberBox.height,unitBoxBottomOffset:unitBox.bottom-numberBox.bottom,
        valueFont:getComputedStyle(number).fontSize,unitFont:getComputedStyle(unit).fontSize};
      const pixels=rect => ctx.getImageData(Math.floor(rect.x*ratio),Math.floor(rect.y*ratio),
        Math.ceil(rect.width*ratio),Math.ceil(rect.height*ratio)).data;
      const normalPixels=pixels(cardBox);
      ctx.drawImage(unclippedImage,0,0);
      const unclippedPixels=pixels(cardBox);
      ctx.drawImage(image,0,0);
      // 与开放溢出的版本对比可见字形，排除文字框边界的抗锯齿色差。
      let clipped=false;
      for(let index=0;index<normalPixels.length;index+=4){
        const original=Math.min(normalPixels[index],normalPixels[index+1],normalPixels[index+2]);
        const exposed=Math.min(unclippedPixels[index],unclippedPixels[index+1],unclippedPixels[index+2]);
        if(exposed>225 && original<180){
          clipped=true;
          break;
        }
      }
      const horizontalOverflow=Array.from(card.querySelectorAll('p')).some(p=>
        p.scrollWidth>p.clientWidth+1);
      return {number:number.textContent,unit:unit.textContent,numberBottom,unitBottom,
        deltaCssPx:unitBottom-numberBottom,font:getComputedStyle(number).fontFamily,
        boxSizing:getComputedStyle(unit).boxSizing,
        unitPaddingBottom:getComputedStyle(unit).paddingBottom,
        unitMarginBottom:getComputedStyle(unit).marginBottom,
        unitHeight:getComputedStyle(unit).height,
        clipped,horizontalOverflow,geometry};
    });
  }, {dataUrl:'data:image/png;base64,' + png.toString('base64'),
    unclippedUrl:'data:image/png;base64,' + unclipped.toString('base64')});
  writeFileSync(path.join(output, 'evidence.json'), JSON.stringify({ width,height,scale,evidence,errors },null,2));
  assert.deepEqual(errors, []);
  for(const [index,sample] of evidence.entries()){
    assert.equal(sample.boxSizing, 'border-box');
    assert.equal(sample.clipped, false);
    assert.equal(sample.horizontalOverflow, false);
    const near=(actual,expected)=>assert(Math.abs(actual-expected)<0.1,
      `几何不符: ${actual} != ${expected}`);
    near(sample.geometry.displayHeight,(height-24)*scale);
    near(sample.geometry.titleTop,12*scale);
    near(sample.geometry.titleHeight,60*scale);
    near(sample.geometry.labelHeight,(index<2 ? 42 : 21)*scale);
    assert.equal(sample.geometry.labelWeight,'500');
    near(sample.geometry.labelCenterOffset,sample.geometry.subtitleHeight ? -9*scale : 0);
    if(sample.geometry.subtitleHeight){
      near(sample.geometry.subtitleHeight,16*scale);
      near(sample.geometry.subtitleGap,2*scale);
      assert.equal(sample.geometry.subtitleFont,'12px');
    }
    near(sample.geometry.gap,4*scale);
    near(sample.geometry.numericAreaHeight,(height-24-60-4)*scale);
    near(sample.geometry.rowHeight,46*scale);
    near(sample.geometry.rowCenterOffset,0);
    near(sample.geometry.valueHeight,46*scale);
    near(sample.geometry.unitBoxBottomOffset,0);
    assert.equal(sample.geometry.valueFont,'46px');
    assert.equal(sample.geometry.unitFont,'16px');
    assert.equal(sample.unitHeight,'21px');
    assert.equal(sample.unitMarginBottom,'0px');
    assert.equal(sample.unitPaddingBottom,'0px');
  }
  console.log(JSON.stringify({passed:evidence.length,width,height,scale,evidence}));
} finally {
  await browser.close();
}
