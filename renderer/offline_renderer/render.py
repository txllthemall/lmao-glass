from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage
import cairosvg

ROOT=Path(__file__).resolve().parents[2]
MASTER=1024
DP_SCALE=MASTER/108.0

def hexrgb(h):
    h=h.lstrip('#'); return np.array([int(h[i:i+2],16) for i in (0,2,4)],dtype=np.float32)/255

def rounded_mask(n=MASTER, margin=62, radius=236):
    im=Image.new('L',(n,n),0); d=ImageDraw.Draw(im)
    d.rounded_rectangle((margin,margin,n-margin,n-margin),radius=radius,fill=255)
    return np.asarray(im,dtype=np.float32)/255

def sample_bilinear(img, x, y):
    # img HxWxC, coordinates x/y float arrays
    h,w=img.shape[:2]
    return np.stack([ndimage.map_coordinates(img[...,c],[y,x],order=1,mode='nearest') for c in range(img.shape[2])],axis=-1)

def virtual_environment(n, tint):
    y,x=np.mgrid[0:n,0:n].astype(np.float32); u=x/(n-1); v=y/(n-1)
    base=np.zeros((n,n,3),np.float32)
    # low-frequency environment, deliberately neutral so transparency survives arbitrary wallpaper
    base[...,0]=0.50+0.08*(1-v)+0.03*np.sin((u+v)*math.pi*2)
    base[...,1]=0.52+0.07*(1-v)+0.02*np.cos(u*math.pi*2)
    base[...,2]=0.56+0.08*(1-v)
    # colored spill, weak
    spill=np.exp(-(((u-.20)/.30)**2+((v-.18)/.28)**2))[...,None]
    base=base*(1-spill*.08)+tint[None,None,:]*(spill*.08)
    return np.clip(base,0,1)

def render_svg(path:Path, scale:float, ox:float, oy:float):
    png=cairosvg.svg2png(bytestring=path.read_bytes(),output_width=MASTER,output_height=MASTER)
    import io
    im=Image.open(io.BytesIO(png)).convert('RGBA')
    # crop nontransparent and optical normalize
    a=np.array(im)[...,3]
    ys,xs=np.where(a>4)
    if len(xs)==0: return im
    crop=im.crop((xs.min(),ys.min(),xs.max()+1,ys.max()+1))
    target=int(MASTER*0.52*scale/0.75)
    ratio=min(target/crop.width,target/crop.height)
    crop=crop.resize((max(1,int(crop.width*ratio)),max(1,int(crop.height*ratio))),Image.Resampling.LANCZOS)
    out=Image.new('RGBA',(MASTER,MASTER),(0,0,0,0))
    x=int((MASTER-crop.width)/2+ox*MASTER); y=int((MASTER-crop.height)/2+oy*MASTER)
    out.alpha_composite(crop,(x,y)); return out

def render_one(slug, cfg, preset):
    n=MASTER
    mask=rounded_mask(n)
    inside=ndimage.distance_transform_edt(mask>0.5)
    band=max(1,preset['refractionBandDp']*DP_SCALE)
    # Kyant-inspired circular edge profile: 1 - sqrt(1-x^2), x from edge inward
    q=np.clip(1.0-inside/band,0,1)
    height=(1-np.sqrt(np.clip(1-q*q,0,1)))*mask
    gy,gx=np.gradient(height)
    nz=np.full_like(gx,0.65)
    norm=np.sqrt(gx*gx+gy*gy+nz*nz)+1e-6
    nx=-gx/norm; ny=-gy/norm; nz=nz/norm
    tint=hexrgb(cfg['tint'])
    env=virtual_environment(n,tint)
    env_img=Image.fromarray((env*255).astype('uint8')).filter(ImageFilter.GaussianBlur(radius=preset['blurDp']*DP_SCALE))
    env=np.asarray(env_img,dtype=np.float32)/255
    y,x=np.mgrid[0:n,0:n].astype(np.float32)
    refr_px=preset['refractionDp']*DP_SCALE
    edge=np.clip(q,0,1)
    sx=x+nx*refr_px*(0.25+0.75*edge); sy=y+ny*refr_px*(0.25+0.75*edge)
    refr=sample_bilinear(env,sx,sy)
    # restrained edge dispersion, only near light-facing edge
    ang=math.radians(preset['highlightAngleDeg']); lx,ly=math.cos(ang),math.sin(ang)
    ndl=np.clip(nx*lx+ny*ly,0,1)
    disp_edge=edge*(ndl**2)
    disp=preset['dispersionDp']*DP_SCALE
    sr=sample_bilinear(env,sx+nx*disp*disp_edge,sy+ny*disp*disp_edge)[...,0]
    sb=sample_bilinear(env,sx-nx*disp*disp_edge,sy-ny*disp*disp_edge)[...,2]
    refr[...,0]=sr; refr[...,2]=sb
    alpha=preset['glassAlpha']*mask
    # broad physically-motivated specular, not a fixed white stripe
    spec=(ndl**(4+18*preset['roughness']))*edge*preset['specular']
    # opposite dark rim and ambient Fresnel-like edge
    opp=np.clip(-(nx*lx+ny*ly),0,1)*edge
    fres=(1-np.clip(nz,0,1))**1.5*edge
    rgb=refr*(0.82+0.18*tint[None,None,:])
    rgb += spec[...,None]*0.50 + fres[...,None]*0.12
    rgb -= opp[...,None]*0.08
    # internal soft shadow immediately inside edge
    shadow=ndimage.gaussian_filter(edge,preset['shadowBlurDp']*DP_SCALE)*preset['shadowAlpha']
    rgb-=shadow[...,None]*0.05
    rng=np.random.default_rng(20260903)
    rgb += rng.normal(0,preset['noise'],(n,n,1)).astype(np.float32)*mask[...,None]
    rgb=np.clip(rgb,0,1)
    # alpha variation tied to optical edge response
    out_a=np.clip(alpha + spec*0.28 + fres*0.13,0,0.62)*mask
    rgba=np.dstack([rgb,out_a])
    base=Image.fromarray((rgba*255).astype('uint8'),'RGBA')
    # subtle internal glyph shadow then glyph
    glyph=render_svg(ROOT/f'artwork/masters/{slug}.svg',cfg['scale'],cfg['offsetX'],cfg['offsetY'])
    ga=np.asarray(glyph,dtype=np.uint8)[...,3]
    sh=Image.fromarray(ga,'L').filter(ImageFilter.GaussianBlur(radius=9))
    shadow_rgba=Image.new('RGBA',(n,n),(0,0,0,0)); shadow_rgba.putalpha(sh.point(lambda p:int(p*0.16)))
    base.alpha_composite(shadow_rgba,(5,8))
    # apply subtle material highlight to colored glyph instead of pasting unchanged
    g=np.asarray(glyph,dtype=np.float32)/255
    g[...,3]*=preset['glyphOpacity']
    local=(0.92+0.10*ndl[...,None])
    g[...,:3]=np.clip(g[...,:3]*local,0,1)
    glyph=Image.fromarray((g*255).astype('uint8'),'RGBA')
    base.alpha_composite(glyph)
    return base, mask, height, np.dstack([(nx*.5+.5),(ny*.5+.5),(nz*.5+.5)])

def save_maps(slug,mask,height,normal):
    Image.fromarray((mask*255).astype('uint8')).save(ROOT/f'artwork/masks/{slug}.png')
    Image.fromarray((height*65535).astype('uint16')).save(ROOT/f'artwork/height/{slug}.png')
    Image.fromarray((normal*255).astype('uint8'),'RGB').save(ROOT/f'artwork/normals/{slug}.png')

def backgrounds(size):
    bg=[]
    for name,color in [('white',(245,245,245)),('black',(14,14,16)),('gray',(120,124,130)),('color',(55,72,155))]:
        bg.append((name,Image.new('RGB',(size,size),color)))
    # synthetic complex wallpaper
    a=np.zeros((size,size,3),np.uint8); y,x=np.mgrid[0:size,0:size]
    a[...,0]=(70+60*np.sin(x/17)+30*np.cos(y/29)).clip(0,255)
    a[...,1]=(80+55*np.sin((x+y)/31)+25*np.cos(x/13)).clip(0,255)
    a[...,2]=(110+70*np.cos(y/21)+25*np.sin(x/9)).clip(0,255)
    bg.append(('complex',Image.fromarray(a)))
    return bg

def contact_sheet(outputs, cfgs):
    cell=190; icon=130; labels=34; cols=5; rows=len(outputs)
    sheet=Image.new('RGB',(cell*cols,rows*(cell+labels)),(232,232,234)); draw=ImageDraw.Draw(sheet)
    bgs=backgrounds(icon)
    for r,(slug,im) in enumerate(outputs.items()):
        small=im.resize((icon,icon),Image.Resampling.LANCZOS)
        for c,(bn,bg) in enumerate(bgs):
            canvas=bg.copy().convert('RGBA'); canvas.alpha_composite(small)
            x=c*cell+(cell-icon)//2; y=r*(cell+labels)+8
            sheet.paste(canvas.convert('RGB'),(x,y)); draw.text((c*cell+8,y+icon+4),bn,fill=(40,40,42))
        draw.text((8,r*(cell+labels)+2),cfgs[slug]['displayName'],fill=(20,20,22))
    sheet.save(ROOT/'generated/contact-sheets/qa-grid.png')

def android_xml(slug):
    v26=f'''<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n    <background android:drawable="@drawable/ic_{slug}_background" />\n    <foreground android:drawable="@drawable/ic_{slug}_foreground" />\n</adaptive-icon>\n'''
    v33=f'''<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n    <background android:drawable="@drawable/ic_{slug}_background" />\n    <foreground android:drawable="@drawable/ic_{slug}_foreground" />\n    <monochrome android:drawable="@drawable/ic_{slug}_monochrome" />\n</adaptive-icon>\n'''
    (ROOT/f'android-pack/src/main/res/mipmap-anydpi-v26/ic_{slug}.xml').write_text(v26)
    (ROOT/f'android-pack/src/main/res/mipmap-anydpi-v33/ic_{slug}.xml').write_text(v33)
    (ROOT/f'android-pack/src/main/res/drawable/ic_{slug}_background.xml').write_text('<?xml version="1.0" encoding="utf-8"?>\n<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle"><solid android:color="#00000000"/></shape>\n')

def ensure_output_dirs():
    for d in [
        ROOT/'android-pack/src/main/res/drawable',
        ROOT/'android-pack/src/main/res/mipmap-anydpi-v26',
        ROOT/'android-pack/src/main/res/mipmap-anydpi-v33',
        ROOT/'android-pack/src/main/assets',
        ROOT/'generated/icons',
        ROOT/'generated/contact-sheets',
        ROOT/'variants/regular',
        ROOT/'artwork/masks',
        ROOT/'artwork/height',
        ROOT/'artwork/normals',
    ]:
        d.mkdir(parents=True,exist_ok=True)

def main():
    ensure_output_dirs()
    cfgs=json.loads((ROOT/'android-pack/launcher-mappings/icons.json').read_text())
    presets=json.loads((ROOT/'renderer/material-presets.json').read_text())
    preset=presets['liquid_regular']; outs={}
    for slug,cfg in cfgs.items():
        im,mask,height,normal=render_one(slug,cfg,preset); outs[slug]=im
        im.save(ROOT/f'generated/icons/{slug}_1024.png')
        im.resize((512,512),Image.Resampling.LANCZOS).save(ROOT/f'variants/regular/{slug}.png')
        save_maps(slug,mask,height,normal); android_xml(slug)
        fg=im.resize((432,432),Image.Resampling.LANCZOS)
        fg.save(ROOT/f'android-pack/src/main/res/drawable/ic_{slug}_foreground.png')
        glyph=render_svg(ROOT/f'artwork/masters/{slug}.svg',cfg['scale'],cfg['offsetX'],cfg['offsetY']).resize((432,432),Image.Resampling.LANCZOS)
        a=glyph.getchannel('A')
        mono=Image.new('RGBA',(432,432),(255,255,255,0)); mono.putalpha(a)
        mono.save(ROOT/f'android-pack/src/main/res/drawable/ic_{slug}_monochrome.png')
    contact_sheet(outs,cfgs)
    print('generated',len(outs),'icons')
if __name__=='__main__': main()
