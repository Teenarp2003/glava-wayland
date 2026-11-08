import importlib.util,json,pathlib,tempfile,unittest,subprocess
from unittest.mock import patch
P=pathlib.Path
spec=importlib.util.spec_from_file_location('manager',P(__file__).resolve().parents[1]/'glava-desktop.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Child:
    def __init__(self,*args,**kwargs):self.code=None;self.terminated=False
    def poll(self):return self.code
    def terminate(self):self.terminated=True;self.code=0
    def wait(self,timeout=None):return self.code
    def kill(self):self.code=-9
class Tests(unittest.TestCase):
    def test_scaled_rotated_and_disconnected_outputs(self):
        data={'outputs':[{'name':'DP-1','enabled':True,'connected':True,'scale':1.5,'rotation':1,'size':{'width':3840,'height':2160}}, {'name':'HDMI-1','enabled':False,'connected':True,'size':{'width':1920,'height':1080}}, {'name':'DP-2','enabled':True,'connected':True,'rotation':2,'size':{'width':1920,'height':1080}}]}
        self.assertEqual(mod.output_geometry(data,{'height':600,'bottom_margin':80}),{'DP-1':(2560,600,760),'DP-2':(1080,600,1240)})
    def test_per_output_panel_clearance(self):
        data={'outputs':[{'name':'DP-1','enabled':True,'connected':True,'scale':1.5,'size':{'width':3840,'height':2160}}]}
        settings={'height':600,'bottom_margin':80,'outputs':{'DP-1':{'bottom_margin':58}}}
        self.assertEqual(mod.output_geometry(data,settings),{'DP-1':(2560,600,782)})
    def panel_fixture(self):
        data={'outputs':[
            {'name':'DP-A','enabled':True,'connected':True,'scale':1.5,'size':{'width':3840,'height':2160},'pos':{'x':1920,'y':0}},
            {'name':'HDMI-B','enabled':True,'connected':True,'scale':1,'size':{'width':1920,'height':1080},'pos':{'x':0,'y':180}}]}
        panels=[{'screen':9,'height':66,'location':'bottom','floating':True,'hiding':'none','geometry':{'x':1920,'y':0,'width':2560,'height':1440}},
                {'screen':2,'height':58,'location':'bottom','floating':True,'hiding':'none','geometry':{'x':0,'y':180,'width':1920,'height':1080}}]
        settings={'height':600,'bottom_margin':80,'auto_panel_margin':True,'panel_extra_gap':0,
                  'outputs':{'DP-A':{'bottom_margin':66},'HDMI-B':{'bottom_margin':80,'panel_extra_gap':22}}}
        return data,panels,settings
    def test_panel_geometry_matches_despite_different_screen_indexes(self):
        data,panels,settings=self.panel_fixture()
        self.assertEqual(mod.output_geometry(data,settings,panels),{'DP-A':(2560,600,774),'HDMI-B':(1920,600,400)})
        panels[0]['height']=74
        self.assertEqual(mod.output_geometry(data,settings,panels),{'DP-A':(2560,600,766),'HDMI-B':(1920,600,400)})
    def test_panel_query_failure_keeps_last_height_and_recovers(self):
        data,panels,settings=self.panel_fixture();new=[dict(panels[0],height=74),panels[1]]
        tracker=mod.PanelTracker()
        with patch.object(mod,'query_panels',side_effect=[panels,subprocess.TimeoutExpired('qdbus6',2),new]):
            self.assertIs(tracker.refresh(),panels)
            self.assertIs(tracker.refresh(),panels)
            self.assertEqual(mod.output_geometry(data,settings,tracker.panels)['DP-A'],(2560,600,774))
            self.assertIs(tracker.refresh(),new)
    def test_manual_fallback_and_per_output_opt_out(self):
        data,panels,settings=self.panel_fixture()
        self.assertEqual(mod.output_geometry(data,settings,None),{'DP-A':(2560,600,774),'HDMI-B':(1920,600,400)})
        settings['outputs']['DP-A']['auto_panel_margin']=False
        panels[0]['height']=120
        self.assertEqual(mod.output_geometry(data,settings,panels)['DP-A'],(2560,600,774))
        panels[1]['location']='top'
        self.assertEqual(mod.output_geometry(data,settings,panels)['HDMI-B'],(1920,600,400))
    def test_panel_resize_only_restarts_affected_output_and_hotplug_rematches(self):
        data,panels,settings=self.panel_fixture();settings.update(fps=60,amplify=600)
        with tempfile.TemporaryDirectory() as tmp, patch.object(mod.subprocess,'Popen',Child):
            root=P(tmp);source=root/'source';(source/'shaders/glava').mkdir(parents=True);templates=P(__file__).resolve().parents[1]
            manager=mod.Manager(source,templates,root/'runtime',settings)
            manager.reconcile(mod.output_geometry(data,settings,panels));first=manager.children['DP-A'][0];second=manager.children['HDMI-B'][0]
            panels[0]['height']=74
            manager.reconcile(mod.output_geometry(data,settings,panels))
            self.assertTrue(first.terminated);self.assertIs(manager.children['HDMI-B'][0],second)
            data['outputs'][0]['enabled']=False
            manager.reconcile(mod.output_geometry(data,settings,panels));self.assertNotIn('DP-A',manager.children);self.assertIs(manager.children['HDMI-B'][0],second)
            data['outputs'][0]['enabled']=True;data['outputs'][0]['pos']={'x':1920,'y':200};panels[0]['geometry']['y']=200;panels[0]['screen']=0
            manager.reconcile(mod.output_geometry(data,settings,panels));self.assertEqual(manager.children['DP-A'][1],(2560,600,766));self.assertIs(manager.children['HDMI-B'][0],second)
            manager.close()
    def test_unplug_replug_and_resize_preserve_other_process(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mod.subprocess,'Popen',Child):
            root=P(tmp);source=root/'source';(source/'shaders/glava').mkdir(parents=True);templates=P(__file__).resolve().parents[1]
            manager=mod.Manager(source,templates,root/'runtime',{'fps':60,'amplify':600})
            desired={'DP-1':(2560,600,760),'HDMI-1':(1920,600,400)}
            manager.reconcile(desired);self.assertEqual(len(manager.children),2)
            first=manager.children['DP-1'][0];second=manager.children['HDMI-1'][0]
            manager.reconcile({'DP-1':desired['DP-1']});self.assertTrue(second.terminated);self.assertIs(manager.children['DP-1'][0],first)
            manager.reconcile(desired);self.assertIsNot(manager.children['HDMI-1'][0],second)
            manager.reconcile({'DP-1':(1920,600,400),'HDMI-1':desired['HDMI-1']});self.assertTrue(first.terminated)
            self.assertIn('#define AMPLIFY 600',(root/'runtime/DP-1/userconf/bars.glsl').read_text())
            self.assertIn('#request setxwintype "bottom"',(root/'runtime/DP-1/userconf/rc.glsl').read_text())
            manager.close();self.assertFalse(manager.children)
if __name__=='__main__':unittest.main()
