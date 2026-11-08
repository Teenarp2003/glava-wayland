import importlib.util,json,pathlib,tempfile,unittest
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
