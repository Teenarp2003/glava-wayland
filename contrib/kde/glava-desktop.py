#!/usr/bin/env python3
"""One native, click-through GLava process per enabled KDE output."""
import argparse,json,math,os,pathlib,re,shutil,signal,subprocess,time
P=pathlib.Path

# Plasma screen indexes need not equal KScreen output indexes, especially after
# hotplug. Query each panel's actual logical screen rectangle instead.
PANEL_SCRIPT = '''var ps=panels();var result=[];for(var i=0;i<ps.length;i++){var p=ps[i];result.push({id:p.id,screen:p.screen,height:p.height,location:p.location,floating:p.floating,hiding:p.hiding,geometry:screenGeometry(p.screen)});}print(JSON.stringify(result));'''

def query_panels():
    result=subprocess.run(['qdbus6','org.kde.plasmashell','/PlasmaShell',
        'org.kde.PlasmaShell.evaluateScript',PANEL_SCRIPT],
        capture_output=True,text=True,timeout=2,check=True)
    panels=json.loads(result.stdout)
    if not isinstance(panels,list):raise ValueError('Plasma panel query was not an array')
    return panels

class PanelTracker:
    """Keep the last valid snapshot during a Plasma reload or D-Bus timeout."""
    def __init__(self):self.panels=None;self.unavailable=False
    def refresh(self):
        try:
            panels=query_panels()
        except (OSError,subprocess.SubprocessError,json.JSONDecodeError,ValueError) as error:
            if not self.unavailable:
                print('Panel query unavailable; using cached heights or configured margins:',error,flush=True)
            self.unavailable=True
        else:
            if self.unavailable:print('Panel height query recovered',flush=True)
            self.panels=panels;self.unavailable=False
        return self.panels

def panel_margin(output,width,height,panels):
    """Return matching bottom-panel height, or None for manual fallback."""
    if panels is None:return None
    pos=output.get('pos',{})
    if 'x' not in pos or 'y' not in pos:return None
    target=(pos['x'],pos['y'],width,height)
    heights=[]
    for panel in panels:
        if not isinstance(panel,dict) or panel.get('location')!='bottom':continue
        rect=panel.get('geometry',{})
        if not isinstance(rect,dict):continue
        try:
            actual=tuple(float(rect[key]) for key in ('x','y','width','height'))
            panel_height=float(panel['height'])
        except (KeyError,TypeError,ValueError):continue
        # A logical-pixel rounding tolerance covers fractional scaling.
        if (math.isfinite(panel_height) and panel_height>0 and
            all(math.isfinite(a) and abs(a-float(b))<=1 for a,b in zip(actual,target))):
            heights.append(math.ceil(panel_height))
    return max(heights) if heights else None

def output_geometry(data, settings, panels=None):
    result={}
    for output in data.get('outputs',[]):
        if not output.get('connected') or not output.get('enabled'):continue
        name=output.get('name')
        mode=next((m for m in output.get('modes',[]) if m.get('id')==output.get('currentModeId')),None)
        size=(mode or {}).get('size',output.get('size',{}))
        if not name or not size.get('width') or not size.get('height'):continue
        scale=float(output.get('scale') or 1)
        w,h=size['width'],size['height']
        if output.get('rotation') in (2,8):w,h=h,w
        w,h=round(w/scale),round(h/scale)
        per_output=settings.get('outputs',{}).get(name,{})
        margin=max(0,int(per_output.get('bottom_margin',settings['bottom_margin'])))
        if per_output.get('auto_panel_margin',settings.get('auto_panel_margin',False)):
            measured=panel_margin(output,w,h,panels)
            if measured is not None:
                gap=max(0,int(per_output.get('panel_extra_gap',settings.get('panel_extra_gap',0))))
                margin=measured+gap
        margin=min(margin,max(0,h-1))
        height=max(1,min(int(settings['height']),h-margin))
        result[name]=(w,height,max(0,h-margin-height))
    return result

class Manager:
    def __init__(self,source,templates,runtime,settings):
        self.source,self.templates,self.runtime,self.settings=source,templates,runtime,settings
        self.children={};self.retry_at={}
        (runtime/'shaders').mkdir(parents=True,exist_ok=True)
        fallback=runtime/'shaders/glava'
        if not fallback.exists():fallback.symlink_to(source/'shaders/glava',target_is_directory=True)
    def stop(self,name):
        proc,geometry,log=self.children.pop(name)
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        log.close();print('Stopped',name,flush=True)
    def reconcile(self,desired):
        for name,(proc,geometry,log) in list(self.children.items()):
            if name not in desired or geometry!=desired[name] or proc.poll() is not None:
                if proc.poll() is not None:self.retry_at[name]=time.monotonic()+3
                self.stop(name)
        for name,geometry in desired.items():
            if name in self.children or time.monotonic()<self.retry_at.get(name,0):continue
            safe=re.sub(r'[^a-zA-Z0-9_.-]','_',name)
            cwd=self.runtime/safe;conf=cwd/'userconf';cwd.mkdir(parents=True,exist_ok=True)
            if conf.exists():shutil.rmtree(conf)
            shutil.copytree(self.source/'shaders/glava',conf)
            rc=(self.templates/'rc.glsl').read_text()
            width,height,y=geometry
            for key,value in {'setgeometry':f'0 {y} {width} {height}','setxwintype':'"bottom"','setclickthrough':'true','setswap':'0','setframerate':str(self.settings['fps']),'setprintframes':'false'}.items():
                rc=re.sub(r'^#request '+key+r' .*$', '#request '+key+' '+value,rc,flags=re.M)
            (conf/'rc.glsl').write_text(rc)
            bars=(self.templates/'bars.glsl').read_text()
            bars=re.sub(r'^#define AMPLIFY .*$', '#define AMPLIFY '+str(self.settings['amplify']),bars,flags=re.M)
            (conf/'bars.glsl').write_text(bars)
            log=(cwd/'glava.log').open('ab',buffering=0)
            env=dict(os.environ,GLAVA_OUTPUT=name)
            try:proc=subprocess.Popen([str(self.source/'build/glava'),'--backend','wayland'],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
            except Exception:log.close();raise
            self.children[name]=(proc,geometry,log)
            print('Started',name,'geometry',geometry,flush=True)
    def close(self):
        for name in list(self.children):self.stop(name)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=P,default=P.home()/'.local/share/alien-glava/source');p.add_argument('--config',type=P,default=P.home()/'.config/alien-glava');a=p.parse_args()
    settings={'height':600,'amplify':600,'bottom_margin':80,'auto_panel_margin':True,'panel_extra_gap':0,'fps':60,'poll_seconds':2}
    if (a.config/'settings.json').exists():settings.update(json.loads((a.config/'settings.json').read_text()))
    runtime=P(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/('alien-glava-'+str(os.getuid()));runtime.mkdir(mode=0o700,parents=True,exist_ok=True)
    manager=Manager(a.source,a.config,runtime,settings);panel_tracker=PanelTracker();stopping=False
    def stop(signum,frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        while not stopping:
            try:
                result=subprocess.run(['kscreen-doctor','-j'],capture_output=True,text=True,timeout=5,check=True)
                data=json.loads(result.stdout)
                needs_panels=settings.get('auto_panel_margin',False) or any(o.get('auto_panel_margin',False) for o in settings.get('outputs',{}).values())
                panels=panel_tracker.refresh() if needs_panels else None
                desired=output_geometry(data,settings,panels)
            except (subprocess.SubprocessError,json.JSONDecodeError,ValueError) as error:
                print('Display query unavailable; preserving current instances:',error,flush=True)
            else:manager.reconcile(desired)
            end=time.monotonic()+max(.5,float(settings['poll_seconds']))
            while not stopping and time.monotonic()<end:time.sleep(.2)
    finally:manager.close()
if __name__=='__main__':main()
