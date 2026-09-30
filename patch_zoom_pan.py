from pathlib import Path

src = Path('Mississippi_Flow_Coverage_Weighted_Tributaries.html')
out = Path('Mississippi_Flow_Coverage_Zoomable_v2.html')
t = src.read_text(encoding='utf-8')

t = t.replace(
    '#map{width:100%;height:min(79vh,1000px);min-height:580px;background:#f5f9fb;border:1px solid #dce7ee;border-radius:9px}',
    '#map{width:100%;height:min(79vh,1000px);min-height:580px;background:#f5f9fb;border:1px solid #dce7ee;border-radius:9px;touch-action:none;cursor:grab;user-select:none}#map.panning{cursor:grabbing}.zoomtools{display:flex;gap:5px;align-items:center}.zoomtools button{min-width:34px;font-weight:700}.zoomhint{font-size:.75rem;color:#617581;margin-top:5px}'
)

t = t.replace(
    '<button id="widthSame">Uniform widths</button></div></div>',
    '<button id="widthSame">Uniform widths</button><span class="zoomtools" aria-label="Map zoom controls"><button id="zoomIn" type="button" title="Zoom in" aria-label="Zoom in">+</button><button id="zoomOut" type="button" title="Zoom out" aria-label="Zoom out">−</button><button id="zoomReset" type="button" title="Reset map view">Reset</button></span></div></div>'
)

t = t.replace(
    '</svg><div class="muted">Generalized georeferenced positions',
    '</svg><div class="zoomhint">Zoom: mouse wheel, trackpad, pinch, or +/− · Pan: drag · Reset: full network</div><div class="muted">Generalized georeferenced positions'
)

needle = "$('widthQ').onclick=()=>{flowWidths=true;$('widthQ').classList.add('active');$('widthSame').classList.remove('active');renderMap()};$('widthSame').onclick=()=>{flowWidths=false;$('widthSame').classList.add('active');$('widthQ').classList.remove('active');renderMap()};\nfunction chart(series){"
nav = r'''$('widthQ').onclick=()=>{flowWidths=true;$('widthQ').classList.add('active');$('widthSame').classList.remove('active');renderMap()};$('widthSame').onclick=()=>{flowWidths=false;$('widthSame').classList.add('active');$('widthQ').classList.remove('active');renderMap()};
// Zoom/pan only changes the SVG viewBox, so flow rendering and click handlers stay intact.
const mapSvg=$('map'),fullView={x:0,y:0,w:1000,h:900};let mapView={...fullView};
let drag=null,dragMoved=false;const touches=new Map();let pinch=null;
function applyMapView(){mapSvg.setAttribute('viewBox',`${mapView.x} ${mapView.y} ${mapView.w} ${mapView.h}`)}
function clampMapView(){
 const minW=145,minH=minW*fullView.h/fullView.w;
 mapView.w=Math.max(minW,Math.min(fullView.w,mapView.w));mapView.h=Math.max(minH,Math.min(fullView.h,mapView.h));
 mapView.x=Math.max(fullView.x,Math.min(fullView.x+fullView.w-mapView.w,mapView.x));
 mapView.y=Math.max(fullView.y,Math.min(fullView.y+fullView.h-mapView.h,mapView.y));
}
function zoomMap(factor,cx=mapView.x+mapView.w/2,cy=mapView.y+mapView.h/2){
 const oldW=mapView.w,oldH=mapView.h,nw=oldW*factor,nh=oldH*factor,rx=(cx-mapView.x)/oldW,ry=(cy-mapView.y)/oldH;
 mapView.x=cx-rx*nw;mapView.y=cy-ry*nh;mapView.w=nw;mapView.h=nh;clampMapView();applyMapView();
}
function resetMap(){mapView={...fullView};applyMapView()}
function clientToSvg(clientX,clientY){const p=mapSvg.createSVGPoint();p.x=clientX;p.y=clientY;return p.matrixTransform(mapSvg.getScreenCTM().inverse())}
$('zoomIn').onclick=()=>zoomMap(.72);$('zoomOut').onclick=()=>zoomMap(1/.72);$('zoomReset').onclick=resetMap;
mapSvg.addEventListener('wheel',e=>{e.preventDefault();const p=clientToSvg(e.clientX,e.clientY);zoomMap(e.deltaY<0?.82:1/.82,p.x,p.y)},{passive:false});
mapSvg.addEventListener('pointerdown',e=>{
 if(e.pointerType==='touch'){touches.set(e.pointerId,{x:e.clientX,y:e.clientY});mapSvg.setPointerCapture(e.pointerId);if(touches.size===2){const a=[...touches.values()];const p1=clientToSvg(a[0].x,a[0].y),p2=clientToSvg(a[1].x,a[1].y);pinch={dist:Math.hypot(p2.x-p1.x,p2.y-p1.y),view:{...mapView},cx:(p1.x+p2.x)/2,cy:(p1.y+p2.y)/2};drag=null}return}
 if(e.button!==0)return;const p=clientToSvg(e.clientX,e.clientY);drag={x:p.x,y:p.y,vx:mapView.x,vy:mapView.y};dragMoved=false;mapSvg.setPointerCapture(e.pointerId);mapSvg.classList.add('panning')
});
mapSvg.addEventListener('pointermove',e=>{
 if(e.pointerType==='touch'&&touches.has(e.pointerId)){touches.set(e.pointerId,{x:e.clientX,y:e.clientY});if(touches.size===2&&pinch){const a=[...touches.values()];const p1=clientToSvg(a[0].x,a[0].y),p2=clientToSvg(a[1].x,a[1].y),d=Math.hypot(p2.x-p1.x,p2.y-p1.y);if(d>0){mapView={...pinch.view};zoomMap(pinch.dist/d,pinch.cx,pinch.cy);dragMoved=true}}return}
 if(!drag)return;const p=clientToSvg(e.clientX,e.clientY),dx=p.x-drag.x,dy=p.y-drag.y;if(Math.hypot(dx,dy)>2)dragMoved=true;mapView.x=drag.vx-dx;mapView.y=drag.vy-dy;clampMapView();applyMapView()
});
function endMapPointer(e){if(e.pointerType==='touch'){touches.delete(e.pointerId);if(touches.size<2)pinch=null;try{mapSvg.releasePointerCapture(e.pointerId)}catch(_){};return}if(!drag)return;drag=null;mapSvg.classList.remove('panning');try{mapSvg.releasePointerCapture(e.pointerId)}catch(_){}}
mapSvg.addEventListener('pointerup',endMapPointer);mapSvg.addEventListener('pointercancel',endMapPointer);
mapSvg.addEventListener('click',e=>{if(dragMoved){e.stopPropagation();e.preventDefault();dragMoved=false}},true);
applyMapView();
function chart(series){'''

if needle not in t:
    raise RuntimeError('Expected insertion point was not found; source file may differ from the weighted-tributary version.')

t = t.replace(needle, nav)
out.write_text(t, encoding='utf-8')
print(f'Wrote {out}')
