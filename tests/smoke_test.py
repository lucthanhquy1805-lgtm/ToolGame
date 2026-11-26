"""Offline smoke test: runs on any OS (Windows APIs are stubbed).

Usage:  python tests/smoke_test.py
Needs numpy, opencv-python(-headless), onnxruntime and the model/*.onnx files.
"""
import sys, types, ctypes, os, json, tempfile, time
sys.stdout.reconfigure(encoding="utf-8")  # Korean monster names in logs (the app logs to a utf-8 file)
# ---- stubs for Windows-only modules ----
class _Fn:
    def __init__(s,ret=0): s.ret=ret; s.argtypes=None
    def __call__(s,*a,**k): return s.ret
class _Dll:
    def __getattr__(s,n): f=_Fn(); setattr(s,n,f); return f
class _Windll:
    def __getattr__(s,n): d=_Dll(); setattr(s,n,d); return d
ctypes.windll=_Windll()
import ctypes.wintypes
for name in ('win32gui','win32con','win32process','pyautogui','keyboard','mss'):
    m=types.ModuleType(name); sys.modules[name]=m
sys.modules['win32con'].SW_RESTORE=9
g=sys.modules['win32gui']
g.IsWindow=lambda h:True; g.ClientToScreen=lambda h,p:(100,50); g.GetClientRect=lambda h:(0,0,1280,960)
g.GetForegroundWindow=lambda:1; g.ShowWindow=lambda *a:None; g.SetForegroundWindow=lambda *a:None
sys.modules['win32process'].GetWindowThreadProcessId=lambda h:(0,1)
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,ROOT); os.chdir(ROOT)
import importlib, pkgutil, lineage_auto
mods=[]
for m in pkgutil.walk_packages(lineage_auto.__path__,'lineage_auto.'):
    importlib.import_module(m.name); mods.append(m.name)
print('imported',len(mods),'modules OK')

from lineage_auto.config import ConfigStore, AppSettings
from lineage_auto.config.models import AccountSettings
from lineage_auto.runtime.context import HotbarPages
d=tempfile.mkdtemp()
# legacy v1 config migration
json.dump({'hp_threshold_pct':40,'skill_hp_enabled':True,'hp_skill_key':'F5','pot_hp_enabled':False,'hp_pot_key':'F7',
  'cursor_hashes':{'sword':'abc','cross':'def'},'skills':{'F8':{'enabled':True,'self_cast':True},'F9':{'enabled':True}},'lang':'en'},
  open(os.path.join(d,'bot_config.json'),'w'))
st=ConfigStore(os.path.join(d,'cfg.json'),os.path.join(d,'bot_config.json'))
s=st.load(); a=s.accounts[0]
assert a.health.threshold_pct==40 and a.cursor_hashes['attack']=='abc' and a.cursor_hashes['corpse']=='def'
assert a.buff('F8').enabled and a.attack('F9').enabled and s.lang=='en'
st.save(s); s2=st.load(); assert s2.to_dict()==s.to_dict(); print('config: legacy import + round-trip OK')
# exclusivity
a.attack('F10').enabled=a.buff('F10').enabled=a.utility('F10').enabled=True; a.enforce_skill_exclusivity()
assert a.buff('F10').enabled and not a.attack('F10').enabled and not a.utility('F10').enabled; print('skill exclusivity OK')

from lineage_auto.skills import get_catalog, classify_role, parse_mp_cost, can_afford_mp
c=get_catalog(); print('catalog skills:',len(c._skills),'elf skills:',len(c.skills_for('elf')),'icon 385:',os.path.basename(c.icon_path('385') or '-'))
assert parse_mp_cost('MP 15')==15 and parse_mp_cost('HP 10')==0 and can_afford_mp(0,5) is False and can_afford_mp(None,5)
assert classify_role('Hồi Máu','',None)=='heal'

from lineage_auto.winapi.cursor import fingerprint_gray, prints_match, hamming_hex
import numpy as np
g1=np.zeros((32,32),np.uint8); g1[4:20,4:12]=255
h1=fingerprint_gray(g1); h2=fingerprint_gray(np.roll(g1,1,axis=1))
print('aHash',h1,h2,'dist',hamming_hex(h1,h2),'match',prints_match(h1,h2))
from lineage_auto.runtime.cursor_profile import CursorProfile
cp=CursorProfile({'attack':h1,'corpse':'','ground':'','npc':''}); assert cp.classify(h1)=='attack' and cp.classify(h2)=='unknown' and cp.ready  # 4 bits off is another cursor (PLAN 0.11)

from lineage_auto.vision import geometry as geo
pts,maxr=geo.sweep_points(640,380,1280,960); print('sweep points',len(pts),'max_r',maxr)

# real YOLOX model through the reconstructed code
from lineage_auto.vision import yolox_mobs
from lineage_auto import hunt_maps
for hm in [m for m in hunt_maps.all_maps() if hunt_maps.model_exists(m.key) or not m.trial]:   # trial models may be absent
    sess=yolox_mobs.ensure_session(hm.key)
    frame=(np.random.default_rng(0).integers(0,255,(960,1280,3))).astype(np.uint8)
    t=time.time(); pts=yolox_mobs.detect_centers(frame,640,380,800,map_key=hm.key)
    print(f'yolox {hm.key}: provider={yolox_mobs.session_device(sess)} out={sess.get_outputs()[0].shape} hits={len(pts)} {1000*(time.time()-t):.0f}ms')

# stat bar on a synthetic HUD using the shipped HP template
import cv2
from lineage_auto.vision.stat_bar import StatBarReader, BarColor
from lineage_auto.winapi.window import ClientRect
tpl=cv2.imread('hp_template.png'); th,tw=tpl.shape[:2]
frame=np.zeros((960,1280,4),np.uint8); y,x=850,300
frame[y:y+th,x:x+tw,:3]=tpl
class G:
    def grab_bgra(s,r): return frame
r=StatBarReader('hp_template.png',BarColor.RED,'HP')
print('HP read on template-only HUD:',r.read_percent(G(),ClientRect(0,0,1280,960)),'% match',round(r.last_match,3))

# feature logic with a fake context
from lineage_auto.features.survival import HealthFeature
from lineage_auto.features.buff import BuffFeature
from lineage_auto.runtime.stats import Stats
class In:
    def __init__(s): s.log=[]
    def double_press(s,k): s.log.append(('dbl',k))
    def press(s,k): s.log.append(('press',k))
    def release_left(s): pass
    def release_all(s): pass
class HR:
    def __init__(s,v): s.v=v; s.last_fill_is_green=False
    def read_percent(s,g,r): return s.v
class Ctx(HotbarPages):
    def __init__(s,acc,hp):
        s.account=acc; s.input=In(); s.hp_reader=HR(hp); s.grabber=None; s.state={}; s.running=True
    def read_mp(s,r): return None
    def read_hp(s,r): s.state['hp_source']='bar'; return s.hp_reader.v
    def can_cast(s,i,r=None): return True
    def log(s,m): print('   log:',m)
    def rect(s): return None
acc=AccountSettings(); ctx=Ctx(acc,30)
h=HealthFeature(ctx); h.tick(None); assert ctx.input.log==[('dbl','F5')]
ctx.hp_reader.v=0
assert not h.check_death(None) and not h.check_death(None) and h.check_death(None); print('health: heal + death confirm OK')
# PLAN 1.3: off by default; on -> heal first, scroll after 2 low reads, pressed once, stop; 0 HP stays "dead"
acc3=AccountSettings(); ctx3=Ctx(acc3,30); h3=HealthFeature(ctx3)
assert not h3.check_death(None) and not h3.check_death(None) and 'F8' not in str(ctx3.input.log)
acc3.health.return_town=True; ctx3.input.log.clear(); h3=HealthFeature(ctx3)
assert not h3.check_death(None) and ctx3.input.log==[('dbl','F5')]
assert h3.check_death(None) and h3.returned and not h3.dead and ctx3.input.log[-1]==('press','F8')
assert h3.check_death(None) and ctx3.input.log.count(('press','F8'))==1
h3.on_start(); ctx3.hp_reader.v=40; assert not h3.check_death(None) and not h3.check_death(None)
ctx3.hp_reader.v=0; h3.check_death(None); h3.check_death(None); assert h3.check_death(None) and h3.dead and not h3.returned
assert AccountSettings.from_dict(acc3.to_dict()).health.return_town; print('health: return to town OK')
# PLAN 1.4: extra potions (off by default), HP/MP, own threshold + cooldown, heal tick wins, one press per tick
acc4=AccountSettings(); assert len(acc4.health.potions)==3 and not any(p.enabled for p in acc4.health.potions)
acc4.health.use_skill=acc4.health.use_potion=False
p0,p1=acc4.health.potions[0],acc4.health.potions[1]
p0.enabled=True; p0.key='F7'; p0.pct=60; p0.cooldown=0.1
p1.enabled=True; p1.stat='mp'; p1.key='F10'; p1.pct=30; p1.cooldown=0.1
ctx4=Ctx(acc4,50); mp4=[20]; ctx4.read_mp=lambda r: mp4[0]; h4=HealthFeature(ctx4)
h4.tick(None); assert ctx4.input.log==[('press','F7')] and h4.just_acted          # HP slot first
h4.tick(None); assert ctx4.input.log[-1]==('press','F10')                          # HP on cooldown -> MP
h4.tick(None); assert len(ctx4.input.log)==2                                        # both cooling down
time.sleep(0.12); ctx4.hp_reader.v=90; h4.tick(None); assert ctx4.input.log[-1]==('press','F10')
time.sleep(0.12); mp4[0]=None; h4.tick(None); assert len(ctx4.input.log)==3          # MP unreadable -> no drink
ctx4.hp_reader.v=0; h4.tick(None); assert len(ctx4.input.log)==3                    # 0 HP = dead, no drink
acc4.health.use_potion=True; ctx4.hp_reader.v=40; h4.tick(None); assert ctx4.input.log[-1]==('press','F6')
d=AccountSettings.from_dict(acc4.to_dict()).health.potions; assert d[1].stat=='mp' and d[1].key=='F10' and len(d)==3
assert len(AccountSettings.from_dict({}).health.potions)==3; print('health: extra potions OK')
# PLAN 1.5: pick-up key only after a kill outcome, off by default, stops when the session stops
from lineage_auto.features.loot import LootFeature
acc5=AccountSettings(); ctx5=Ctx(acc5,100); lf=LootFeature(ctx5)
assert not acc5.loot.enabled and not lf.after_fight('corpse_cursor') and ctx5.input.log==[]
acc5.loot.mode='walk_f4'; acc5.loot.gap=0.01  # PLAN 0.27 / 7: the mode decides (enabled mirrors it)
for o in ('lost','cap','stopped','char_dead','town',None): assert not lf.after_fight(o)
assert lf.after_fight('die_box') and ctx5.input.log==[('press','F4')]*2 and ctx5.state['loot_presses']==2
ctx5.running=False; assert not lf.after_fight('frozen') and len(ctx5.input.log)==2
l=AccountSettings.from_dict(acc5.to_dict()).loot; assert l.enabled and l.mode=='walk_f4' and l.key=='F4' and l.presses==2
assert not AccountSettings.from_dict({}).loot.enabled and AccountSettings.from_dict({}).loot.mode=='auto'
assert AccountSettings.from_dict({'loot':{'enabled':True}}).loot.mode=='walk_f4'  # v11 config "press F4" kept
from lineage_auto.features.loot import suggest_mode
assert suggest_mode(3,3) is None and suggest_mode(10,9)=='auto' and suggest_mode(10,1)=='walk_f4'
print('loot: modes + F4 after kill OK')
acc.buff('F9').enabled=True; acc.buff('F9').skill_id='385'; acc.buff('F9').duration_min=20
ctx2=Ctx(acc,100); b=BuffFeature(ctx2,health=None,icon_present=lambda sid:True,cast_gap=0)
b.on_start(); assert ctx2.input.log==[('dbl','F9')] and b.remaining('F9')>1190
b.tick(None); assert len(ctx2.input.log)==1
# PLAN 2.1b: a "buff ran out" chat line recasts that slot at once (the timer still said 20 min left)
ctx2.state['buff_gone']=['385','399']
b.tick(None); assert ctx2.input.log==[('dbl','F9'),('dbl','F9')] and ctx2.state['buff_gone']==[]
b.tick(None); assert len(ctx2.input.log)==2                      # nothing new in the chat: timer again
# the real picture cut from records_game/20261126_101941_hunt reads back as its skill, and only it
from lineage_auto.vision import name_reader as nr
import numpy as np
tpl=[(sid,m) for sid,m in nr.buff_gone_templates() if sid=='399'][0][1]
assert nr.buff_gone_skill(tpl)=='399' and nr.buff_gone_skill(np.zeros_like(tpl)) is None
assert nr.buff_gone_skill(tpl[:, :int(tpl.shape[1]*0.6)]) is None          # a shorter line is another line
print('buff: start cast + timer hold + chat "ran out" recast OK')
# PLAN 0.1: unconfirmed detections -> rescan N-1 times, then wander; missed spots are not re-hovered
import contextlib
from lineage_auto.features import targeting as tg
from lineage_auto.runtime.session import AccountSession, SessionState
from lineage_auto.config.models import ScanSettings
assert AccountSettings.from_dict(AccountSettings().to_dict()).scan==ScanSettings()
assert AccountSettings.from_dict({}).scan.misses_before_wander==2  # old configs get the defaults
fake_hits=[(760+30*i,380) for i in range(10)]                   # 10 false detections (NPC, rocks...) > 100 px away
tg.detect_centers=lambda *a,**k: list(fake_hits)
tg.CursorProbe.current_hash=staticmethod(lambda: 'ground')     # never the attack cursor
class Cur:
    ready=True
    cast_registered=False          # PLAN 0.34: no aiming cursor registered -> the old blind wait
    aim=True                       # what the ellipse probe sees when it is registered
    def is_attack(s,h): return h=='attack'
    def is_corpse(s,h): return h=='corpse'
    def is_registered(s,kind): return bool(s.cast_registered) if kind=='cast' else True
    def is_cast(s,h): return bool(s.aim)
class Mv:
    def __init__(s): s.moves=[]
    def move(s,x,y): s.moves.append((x,y))
    def release_left(s): pass
    def release_all(s): pass
class Win:
    def is_alive(s): return True
    def is_foreground(s): return True
class Arb:
    @contextlib.contextmanager
    def hold(s,i,timeout=0): yield True
class TCtx(HotbarPages):
    def __init__(s):
        s.account=AccountSettings(); s.running=True; s.input=Mv(); s.cursors=Cur(); s.window=Win(); s.arbiter=Arb()
        s.recorder=None; s.state={}; s.stats=Stats()        # PLAN 4.1: BotContext carries one
        s.grabber=types.SimpleNamespace(grab_bgr=lambda r: np.zeros((960,1280,3),np.uint8), close_thread=lambda:None)
    def request_stop(s): s.running=False
    def sleep(s,t): time.sleep(t); return s.running
    def log(s,m): print('   log:',m)
    def rect(s): return ClientRect(0,0,1280,960)
    def char_pos(s,r): return (640,380)
    def read_hud(s,r): return {'hp':None,'mp':None}
class Noop:
    def tick(s,*a): pass
    def check_death(s,*a): return False
    def on_stop(s): pass
    def after_fight(s,*a): return False
tctx=TCtx(); tf=tg.TargetingFeature(tctx)
calls=[]
class Expl(Noop):
    def wander(s,r,c): calls.append('wander'); tctx.running=False
    def observe(s): pass
sess=object.__new__(AccountSession)
sess.ctx=tctx; sess.account=tctx.account; sess.state=SessionState.RUNNING; sess.on_state_change=None; sess._deadline=None
from lineage_auto.features.grid_scan import GridScanFeature
sess.grid=GridScanFeature(tctx)
sess.cure=sess.health=sess.buff=sess.combat=sess.loot=Noop(); sess.exploration=Expl(); sess.targeting=tf
orig_acquire=tf.acquire
def counted(r,c): calls.append('scan'); return orig_acquire(r,c)
tf.acquire=counted
t=time.time(); sess._run(); dt=time.time()-t
assert calls==['scan','scan','wander'], calls
moves=tctx.input.moves; assert len(moves)==4 and len(set(moves))==4, moves   # PLAN 0.31: 2 nearest per scan, then 2 not yet missed
assert tf.miss_streak==0 and not tf._misses                    # reset before wander
print(f'scan: 2 unconfirmed scans -> wander OK ({dt/2:.2f}s per failed scan)')
assert dt/2<1.5, dt
# a confirmed target resets the streak; a scan with no detections at all goes straight to wander
tctx.running=True; tf.miss_streak=1
tg.CursorProbe.current_hash=staticmethod(lambda: 'attack')
assert orig_acquire(tctx.rect(),(640,380)) is not None and tf.miss_streak==0
fake_hits.clear(); assert orig_acquire(tctx.rect(),(640,380)) is None and not tf.should_rescan()
print('scan: streak reset on hit / empty scan wanders OK')
# PLAN 0.6 recorder: mode 2 (while hunting) logs scans + hover labels, mode 1 (observe) saves frames, no input
from lineage_auto.runtime import recorder as recmod
from lineage_auto.runtime.manager import SessionManager
import subprocess
Cur.classify=lambda s,h,md5=None: {'attack':'attack','ground':'ground'}.get(h)
rroot=tempfile.mkdtemp()
# PLAN 0.31: within 100 px nothing is skipped and the bot rescans 3 more times before wandering; the box on the
# character itself (< 25 px) is never a candidate
fake_hits[:]=[(645,382),(700,380),(720,380)]
tg.CursorProbe.current_hash=staticmethod(lambda: 'ground')
tctx.running=True; tctx.input.moves.clear(); calls.clear(); sess._run()
assert calls==['scan']*5+['wander'] and set(tctx.input.moves)=={(700,380),(720,380)}, (calls,tctx.input.moves)
print('scan: near boxes rescanned, never skipped, self box dropped OK')
fake_hits[:]=[(760+30*i,380) for i in range(10)]
tctx.running=True; tctx.input.moves.clear(); calls.clear()
tctx.account.record.interval_sec=0.5
tctx.recorder=recmod.Recorder(tctx.account,'hunt',rect=tctx.rect(),root=rroot)
hunt_dir=tctx.recorder.path
sess._run()
assert tctx.recorder is None                                     # closed in _run's finally
summ=json.load(open(os.path.join(hunt_dir,'summary.json')))
assert summ['counts']['hover_ground']==4 and summ['counts']['rescan']==1 and summ['counts']['wander']==1 and summ['hover_confirm_rate']==0, summ
hov=[json.loads(l) for l in open(os.path.join(hunt_dir,'hovers.jsonl'))]
assert len(hov)==4 and hov[0]['frame']=='f_00001.jpg' and hov[0]['kind']=='ground' and hov[-1]['scan']==2, hov[-1]
print('record while hunting: hovers + summary OK', summ['counts'])
# observe: no mouse moves, frames capped by max_frames, ESC/stop_all does not stop it
octx=TCtx(); octx.account.record.interval_sec=0.5; octx.account.record.max_frames=3; octx.window.attached=True
octx.account.hunt_map='dragon_valley'
osess=object.__new__(AccountSession); osess.ctx=octx; osess.account=octx.account; osess.on_state_change=None
osess.state=SessionState.OBSERVING; osess._thread=None; osess._deadline=None
octx.recorder=recmod.Recorder(octx.account,'observe',rect=octx.rect(),root=rroot)
obs_dir=octx.recorder.path
mgr=object.__new__(SessionManager); mgr._sessions={'a':osess}; mgr.stop_all(); assert octx.running   # ESC ignored
t=time.time(); osess._run_observe(); dt=time.time()-t
assert octx.input.moves==[] and osess.state==SessionState.STOPPED
fr=[json.loads(l) for l in open(os.path.join(obs_dir,'frames.jsonl'))]
assert len(fr)==3 and all(os.path.exists(os.path.join(obs_dir,f['file'])) for f in fr) and fr[0]['detect_ms']>0
print(f'observe: 3 frames, no input, ESC ignored OK ({dt:.1f}s)')
z=recmod.zip_record(obs_dir); assert os.path.getsize(z)>0
out=subprocess.run([sys.executable,'tests/analyze_records.py',hunt_dir],capture_output=True,text=True)
assert out.returncode==0 and 'precision 0%' in out.stdout, out.stdout+out.stderr
out=subprocess.run([sys.executable,'tests/analyze_records.py',z],capture_output=True,text=True)
assert out.returncode==0 and 'frames 3' in out.stdout, out.stdout+out.stderr
print('analyze_records on folder + zip OK')
# PLAN 0.2: pick the game window by process (LC.exe), never File Explorer / browser / tool
from lineage_auto.winapi.window import WindowPicker as WP
wins={'lineage_auto_src - File Explorer (869x1032) [explorer.exe:25888]':1,
      'Lineage Classic (1296x999) [lc.exe:100]':2,'Lineage Classic (1296x999) [lc.exe:200]':3,
      'Lineage wiki - Chrome (1936x1048) [chrome.exe:7]':4,'LC (1296x999) [?:9]':5}
assert WP.guess_game_titles(wins)==['Lineage Classic (1296x999) [lc.exe:100]','Lineage Classic (1296x999) [lc.exe:200]']
del wins['Lineage Classic (1296x999) [lc.exe:100]'], wins['Lineage Classic (1296x999) [lc.exe:200]']
assert WP.guess_game_titles(wins)==[]                       # no LC.exe: explorer/chrome never guessed
wins['Lineage II (800x600) [?:11]']=6                         # unreadable exe: fall back to the title
assert WP.guess_game_titles(wins)==['Lineage II (800x600) [?:11]']
assert WP.label_exe('old style (1280x960)')=='' and WP.label_exe('a [b] (1x1) [LC.exe:5]')=='lc.exe'
print('window picker: LC.exe first, explorer/browser excluded OK')
# PLAN 0.3: exact HUD "HP:x/y" text -> fast, trustworthy character death
sys.path.insert(0,os.path.join(ROOT,'tests'))
from build_hud_glyphs import TRUTH as HUD_TRUTH
from lineage_auto.vision import hud_numbers as hn
from lineage_auto.runtime.context import BotContext
hud=hn.HudNumberReader(); assert hud.available
for f,(h,m) in HUD_TRUTH.items():
    v=hud.read(cv2.imread('docs/game_reference/'+f))
    assert v=={'hp':tuple(map(int,h.split('/'))),'mp':tuple(map(int,m.split('/')))}, (f,v)
assert hn.percent((1,432))==1 and hn.percent((0,432))==0 and hn.parse_pair('5/3') is None
def hud_frame(hp_text):
    """frame_0030 with the HP digits replaced by hp_text (glyph templates pasted in place)."""
    fr=cv2.imread('docs/game_reference/frame_0030s.png'); bg=fr[765:777,428:438].copy()
    for k in range(11):
        x=438+30+10*k
        cell=bg if k>=len(hp_text) else cv2.cvtColor(cv2.imread(os.path.join(hn.GLYPH_DIR,hn.glyph_file(hp_text[k])),0),cv2.COLOR_GRAY2BGR)
        fr[765:777,x:x+10]=cell
    return fr
assert hud.read(hud_frame('0/432'))['hp']==(0,432) and hud.read(hud_frame('7/432'))['hp']==(7,432)
recmod.records_root=lambda: rroot                                 # death screenshots go to the temp dir
dctx=object.__new__(BotContext)
dctx.account=AccountSettings(); dctx.account.health.use_skill=dctx.account.health.use_potion=False   # healing off
dctx.hud=hud; dctx._hud_cache=(0.0,None); dctx.state={}; dctx.input=In(); dctx.hp_reader=HR(100)
dctx.mp_reader=types.SimpleNamespace(available=False)
hf_logs=[]
dctx.log=lambda m: (hf_logs.append(m), print('   log:',m))[0]
frame_now={'f':hud_frame('1/432')}
dctx.grabber=types.SimpleNamespace(grab_bgr=lambda r: frame_now['f'])
hf=HealthFeature(dctx)
assert not hf.check_death(None) and hf.last_hp==1 and dctx.state['hp_source']=='hud'      # 1 HP: alive
frame_now['f']=hud_frame('0/432'); time.sleep(0.06)
assert not hf.check_death(None); time.sleep(0.06)
assert hf.check_death(None), 'HUD HP:0 twice = dead (bar would need 3 and healing on)'
deaths=sorted(os.listdir(os.path.join(rroot,'deaths')))       # PLAN 0.3: 3 raw pictures of the death screen
assert len(deaths)==3 and all(f.startswith('death_') and f.endswith('.png') for f in deaths), deaths
assert recmod.latest_record(rroot).endswith('_observe')
assert dctx.input.log==[] and any('WARNING' in m for m in hf_logs), (dctx.input.log, hf_logs)  # no key, WARNING
# PLAN 0.3 (user 26/11): HUD HP low and then gone = SAFE STOP "HUD lost", never a death (a loading screen or
# a dialog over the HUD looks the same); a dark screen or another map name only restarts the 2 s timer.
import lineage_auto.features.survival as sv
sv.HUD_GONE_DEAD_SEC=0.05
dctx.state={}; dctx._hud_cache=(0.0,None); dctx.account.health.read_hud_numbers=True
frame_now['f']=hud_frame('40/432'); hf2=HealthFeature(dctx)
assert not hf2.check_death(None) and dctx.state['hp_abs']==(40,432)
dark=hud_frame(''); dark[:]=5                                         # loading / teleport screen: all black
dctx._hud_cache=(0.0,None); frame_now['f']=dark
assert not hf2.check_death(None); time.sleep(0.06); dctx._hud_cache=(0.0,None)
assert not hf2.check_death(None) and not hf2.hud_lost, 'a dark screen must not stop the hunt'
assert any('dark' in m for m in hf_logs), hf_logs[-3:]
dctx._hud_cache=(0.0,None); frame_now['f']=hud_frame('')              # HUD numbers gone, the ground still there
assert not hf2.check_death(None); time.sleep(0.06); dctx._hud_cache=(0.0,None)
assert hf2.check_death(None) and hf2.hud_lost and not hf2.dead and dctx.input.log==[], dctx.input.log
assert any('WARNING' in m and 'not counted as a death' in m for m in hf_logs), hf_logs[-3:]
assert len([f for f in os.listdir(os.path.join(rroot,'deaths')) if f.startswith('hud_lost_')])==3
sv.HUD_GONE_DEAD_SEC=2.0
dctx.account.health.read_hud_numbers=False; dctx._hud_cache=(0.0,None)
assert dctx.read_hp(None)==100 and dctx.state['hp_source']=='bar'                        # toggle off -> bar
print('hud numbers: HP:0 -> dead in 2 reads, HUD gone -> safe stop (dark screen waits), snapshots OK')
# PLAN 0.4: why a fight ended - corpse cursor / YOLOX die box at the lock / body frozen / lost
from lineage_auto.features import combat as cb
from lineage_auto.features.targeting import Target
cb.BURST_INTERVAL=0; cb.HOLD_MOVE_SETTLE=cb.HOLD_DOWN_SETTLE=0
class CIn:
    def __getattr__(s,n): return lambda *a,**k: None
class FakeTg:
    def __init__(s,track,crops,dies=(),kill_at=None):
        s.track=list(track); s.crops=list(crops); s.last_dies=list(dies); s.last_figures=[]
        s.kill_at=kill_at; s.pops=0; s.kill_watch=None; s.blocked=[]; s.closer=None; s.locks=[]; s.lines=1
        s.probe_ok=True; s.probed=[]; s.last_monsters=[]
    def pop_kills(s):  # PLAN 0.27: a kill line shows on the kill_at-th call (s.lines lines: a splash kill)
        s.pops+=1; return [(time.time(),'오염된 오크 전사')]*s.lines if s.pops==s.kill_at else []
    def closer_than(s,anchor,char): return s.closer
    def probe(s,points,rect):  # PLAN 0.32: the switch candidate is hover-confirmed; s.probe_ok says what it saw
        s.probed=list(points); return Target(*points[0],*points[0]) if s.probe_ok else None
    def route(s,xy): return None,None
    def world(s,xy): return None
    def block(s,xy): s.blocked.append(xy)
    def read_name(s,xy): return None
    def track_current(s,rect,anchor,char=None):
        v=s.track.pop(0) if s.track else None
        return None if v is None else Target(v[0],v[1],v[0],v[1])
    def crop_gray_at(s,rect,xy): return s.crops.pop(0) if s.crops else np.zeros((80,80),np.uint8)
    def note_lock(s,xy): s.locks.append(xy)
    def clear_lock(s): pass
    def reacquire_near(s,rect,char,anchor): return Target(*anchor,*anchor)   # PLAN 1.6: nameplate under the lock
def fight(cursor, track, crops=(), dies=(), dead_char=False, kill_at=None, tgo=None, start=(700,400), mode='auto', melee_max=25.0, cf=None):
    c=TCtx(); c.input=CIn(); c.state={}; c.character=c.account.character; c.can_cast=lambda *a: True; c.account.loot.mode=mode
    c.account.scan.melee_max_sec=melee_max
    c.recorder=recmod.Recorder(c.account,'hunt',rect=c.rect(),root=rroot)
    tg.CursorProbe.current_hash=staticmethod(lambda: cursor)
    h=types.SimpleNamespace(check_death=lambda r: dead_char, just_acted=False)
    f=cf or cb.CombatFeature(c,health=h,targeting=tgo or FakeTg(track,crops,dies,kill_at))
    f.ctx=c; f.targeting=tgo or f.targeting
    cb.CursorProbe.current_hash=tg.CursorProbe.current_hash
    f.engage(Target(*start,*start),c.rect(),(640,380))
    return f.last_outcome, c.state.get('kills',0), c.recorder.counts
moving=[np.full((80,80),v,np.uint8) for v in (0,60,0,60)]; still=[np.full((80,80),9,np.uint8)]*6
assert fight('corpse',[])[:2]==('corpse_cursor',1)
assert fight('ground',[(700,400)]*500,dies=[(712,418)])[:2]==('cap',0)     # monster box still there: not dead
assert fight('ground',[None],dies=[(712,418)])[:2]==('die_box',1)             # box gone + die box at lock
cb.BOX_GONE_SEC=0
# PLAN 0.27: box gone at the lock for BOX_GONE_SEC, chat not readable -> vanished = kill
assert fight('ground',[None,None],dies=[(900,700)])[:2]==('vanished',1)
o=fight('ground',[(700,400)]*20,kill_at=4); assert o[:2]==('chat_kill',1) and o[2]['end_chat_kill']==1  # kill line
# PLAN 0.32: box gone while the cursor still reads "attack" -> leave at once (v14 stood there for the melee cap)
assert fight('attack',[None]*200)[:2]==('vanished',1)
chat_ok=FakeTg([None,None],[]); chat_ok.kill_watch=types.SimpleNamespace(last_lines=5,readable=True)
assert fight('ground',[],tgo=chat_ok)[0]=='gone'          # auto-to-bag server, chat read, no kill line: walked off
chat_ok=FakeTg([None,None],[]); chat_ok.kill_watch=types.SimpleNamespace(last_lines=5,readable=True)
assert fight('ground',[],tgo=chat_ok,mode='walk_f4')[:2]==('vanished',1)  # drop server: the fall is the kill
cb.BOX_GONE_SEC=1.0; cb.NO_SWORD_SEC=0
# PLAN 0.32: lock inside melee range, box still detected, but no attack cursor -> hitting nothing, leave
assert fight('ground',[(700,400)]*500,dies=[(712,418)])[0]=='lost'
cb.NO_SWORD_SEC=1.0
cb.UNREACH_SEC=0; cb.DETOUR_AFTER=10
far=FakeTg([(720,400)]*400,[]); o=fight('ground',[],tgo=far)
assert o[:2]==('unreachable',0) and far.blocked==[(720,400)], o                    # 80 px (beyond melee), never closer
assert fight('ground',[(900,400)]*400,start=(720,400))[0]=='lost'     # 80 px -> 260 px: ran off, lost (no blacklist)
cb.UNREACH_SEC=1.5; cb.DETOUR_AFTER=0.8
# PLAN 0.31: MELEE (lock < 70 px + sword) never side steps / gives up / blacklists; only the melee cap ends it
cb.SIDESTEP_AFTER=0; cb.NO_PROGRESS_SEC=0
mel=FakeTg([(700,400)]*400,[]); o=fight('attack',[],tgo=mel)
assert o[0]=='cap' and 'sidestep' not in o[2] and not mel.blocked, o
o=fight('attack',[(700,400)]*400,melee_max=0.0); assert o[0]=='cap', o                  # melee cap (scan.melee_max_sec)
# ... the PLAN 0.28 rules stay for a lock still far away (122 px, sword up, never closer): side step, then leave
cb.UNREACH_SEC=99; far=FakeTg([(760,400)]*400,[]); o=fight('attack',[],tgo=far,start=(760,400))
assert o[:2]==('no_progress',0) and far.blocked==[(760,400)], o
ev=[json.loads(l) for l in open(os.path.join(recmod.latest_record(rroot),'events.jsonl'),encoding='utf-8')]
assert ev[-1]['melee'] is False and ev[-1]['dist']==122 and ev[-1]['kill_source']=='none', ev[-1]
cb.NO_PROGRESS_SEC=99; o=fight('attack',[(760,400)]*500,start=(760,400)); assert o[0]=='cap' and o[2]['sidestep']==1, o
cb.UNREACH_SEC=1.5; cb.SIDESTEP_AFTER=5.0; cb.NO_PROGRESS_SEC=8.0
# PLAN 0.31 / 2: a monster much closer than the lock, next to the character -> leave for it (lock moved there)
sw=FakeTg([(760,400)]*20,[]); sw.closer=(660,392); o=fight('attack',[],tgo=sw,start=(760,400))
assert o[0]=='switch' and sw.locks[-1]==(660,392) and o[1]==0 and sw.probed==[(660,392)], (o,sw.locks)
# PLAN 0.32: the same box with no attack cursor on it (own sprite / pet / another player) -> stay on the lock
sw=FakeTg([(760,400)]*500,[]); sw.closer=(660,392); sw.probe_ok=False; o=fight('attack',[],tgo=sw,start=(760,400))
assert o[0]=='cap' and sw.locks[-1]==(760,400), (o,sw.locks)
# PLAN 0.31 / 3: one kill = one count. A splash kill with 2 lines = 2; corpse + a line <= 3 s later = 1 (chat);
# no_progress + a late line = 1 (chat); no_progress without a line = 0
spl=FakeTg([(700,400)]*20,[],kill_at=3); spl.lines=2; o=fight('ground',[],tgo=spl)
assert o[0]=='chat_kill' and o[1]==2 and o[2]['kills_chat']==2, o
cb.BOX_GONE_SEC=0  # the box of these fights goes away at once; its kill must still be counted
cf=cb.CombatFeature(TCtx(),targeting=FakeTg([],[]))
o=fight('corpse',[],cf=cf); assert o[:2]==('corpse_cursor',1) and cf.ctx.state['kills_corpse_only']==1
late=FakeTg([(700,400)]*5,[],kill_at=1); o=fight('ground',[],tgo=late,cf=cf)               # its line comes now
assert cf.ctx.state['kills_chat']==1 and cf.ctx.state['kills_corpse_only']==0 and o[1]==1 and o[0]!='chat_kill', (o,cf.ctx.state)
cb.NO_PROGRESS_SEC=0; cb.UNREACH_SEC=99
cf=cb.CombatFeature(TCtx(),targeting=FakeTg([],[]))
o=fight('ground',[],tgo=FakeTg([(760,400)]*400,[]),start=(760,400),cf=cf); assert o[:2]==('no_progress',0), o
fight('ground',[],tgo=FakeTg([(760,400)]*400,[],kill_at=1),start=(760,400),cf=cf)
assert cf.ctx.state['kills']==1 and cf.ctx.state['kills_chat']==1, cf.ctx.state
cb.NO_PROGRESS_SEC=8.0; cb.UNREACH_SEC=1.5
print('combat 0.31: melee kept / far rules / switch / kill tally (splash 2, corpse+chat 1, late chat 1) OK')
r=recmod.Recorder(TCtx().account,'hunt',root=rroot); r.fight('chat_kill',4,True); r.fight('vanished',2,True); r.fight('no_progress',8)
assert r.summary()['fights']=={'kill_chat':{'n':1,'avg_s':4.0},'kill_fall':{'n':1,'avg_s':2.0},'no_progress':{'n':1,'avg_s':8.0}}, r.summary()['fights']
assert fight('ground',[(700,400)]*12,crops=moving+still)[:2]==('frozen',1)    # moved, then 4 still beats
assert fight('attack',[(700,400)]*12,crops=moving+still+still)[0]!='frozen'   # sword still up: keep hitting
o=fight('corpse',[],dead_char=True); assert o[:2]==('char_dead',0) and o[2]=={'end_char_dead':1}
print('combat outcomes: corpse cursor / die box / frozen / chat kill / vanished / unreachable / lost / char dead OK')
# PLAN 0.8c grid sweep: YOLOX 0 -> hover a grid, label sword points, never click; then wander as before
import math
from lineage_auto.features.grid_scan import grid_points
from lineage_auto.config.models import RecordSettings
pts=grid_points(640,380,1280,960,40,200); assert pts and (640,380) not in pts and all(math.hypot(x-640,y-380)<=200 for x,y in pts)
assert math.hypot(pts[0][0]-640,pts[0][1]-380)==40                       # nearest first
fake_hits.clear(); tctx.running=True; tctx.input.moves.clear(); calls.clear(); tf.last_skipped=0
tctx.account.record.grid_scan=True
tg.CursorProbe.current_hash=staticmethod(lambda: 'attack' if tctx.input.moves and tctx.input.moves[-1][0]>700 else 'ground')
tctx.recorder=recmod.Recorder(tctx.account,'hunt',rect=tctx.rect(),root=rroot); gdir=tctx.recorder.path
sess._run()
assert calls==['scan','wander'] and len(tctx.input.moves)==len(pts), (calls,len(tctx.input.moves))
gs=json.load(open(os.path.join(gdir,'summary.json')))['counts']
gh=[json.loads(l) for l in open(os.path.join(gdir,'hovers.jsonl'))]
assert gs['grid_sweeps']==1 and gs['grid_points']==len(pts) and gs['grid_attack']>0 and 'hover_attack' not in gs, gs
assert all(h['src']=='grid' and h['frame'] for h in gh)
gf=[json.loads(l) for l in open(os.path.join(gdir,'frames.jsonl'))]; assert gf[-1]['grid']==len(pts) and 'night' in gf[-1]
tctx.account.record.grid_scan=False
print(f"grid sweep: {len(pts)} points, {gs['grid_attack']} sword labels, no click OK")
out=subprocess.run([sys.executable,'tests/analyze_records.py',gdir,hunt_dir],capture_output=True,text=True,encoding='utf-8')
assert out.returncode==0 and 'grid points' in out.stdout and 'totals per hunting ground' in out.stdout, out.stdout+out.stderr
glab=json.load(open(os.path.join(gdir,'labels.json'),encoding='utf-8'))['images'][gf[-1]['file']]
assert 0<len(glab['monster'])<gs['grid_attack'] and glab['boxes']==[] and 'map' in glab, glab   # grid hits merged per monster
# PLAN 0.7 auto stop: deadline passed -> loop ends at once
tctx.running=True; calls.clear(); sess._deadline=time.monotonic()-1; sess._run(); assert calls==[]; sess._deadline=None
# PLAN 0.38 (24/7): one bad beat is logged and the loop goes on; it does not end the run
class Boom(Noop):
    n=0
    def tick(s,r):
        Boom.n+=1
        if Boom.n==1: raise RuntimeError('boom')
sess.cure=Boom(); tctx.running=True; calls.clear(); sess._run(); sess.cure=Noop()
assert Boom.n>=2 and calls[-1]=='wander' and sess.state!=SessionState.ERROR, (Boom.n, calls, sess.state)
sess.state=SessionState.RUNNING
assert RecordSettings.from_dict({}).auto_stop_min==0 and RecordSettings.from_dict({}).max_gb==5.0 and RecordSettings.from_dict({'stop_key':'F12'}).stop_key=='Pause'
# observe: no model, player's cursor + events (corpse cross, HP 0), stop key / STOP file stop observe too
import itertools
Cur.classify=lambda s,h,md5=None: h if h in ('attack','corpse','ground') else None
seq=itertools.chain(['ground','corpse','corpse','ground'],itertools.repeat('ground'))
def fake_cursor():
    tg.CursorProbe.last_pos=(700,400); return next(seq)
tg.CursorProbe.current_hash=staticmethod(fake_cursor)
octx2=TCtx(); octx2.window.attached=True; octx2.account.record.no_model=True; octx2.account.record.real_map='오염된 축복의 땅'
octx2.account.record.interval_sec=60; octx2.account.record.max_frames=3
hud_seq=itertools.chain([None,None,None,(0,190)],itertools.repeat((5,190)))
octx2.read_hud=lambda r: {'hp':next(hud_seq),'mp':None}
osess2=object.__new__(AccountSession); osess2.ctx=octx2; osess2.account=octx2.account; osess2.on_state_change=None
osess2.state=SessionState.OBSERVING; osess2._thread=None; osess2._deadline=None
octx2.recorder=recmod.Recorder(octx2.account,'observe',rect=octx2.rect(),root=rroot); o2=octx2.recorder.path
osess2._run_observe()
fr=[json.loads(l) for l in open(os.path.join(o2,'frames.jsonl'),encoding='utf-8')]
assert [f.get('event') for f in fr]==[None,'corpse','hp0',None,None], fr   # PLAN 0.19: event frames are outside the 3-frame cap
assert fr[0]['mouse']==[700,400] and fr[0]['cursor']=='ground' and fr[1]['cursor']=='corpse' and fr[0]['hits']==[] and fr[0]['detect_ms'] is None
assert fr[0]['real_map']=='오염된 축복의 땅' and json.load(open(os.path.join(o2,'meta.json'),encoding='utf-8'))['model'] is None
print('observe: no model, cursor labels, corpse/HP0 event frames OK')
osess.state=SessionState.OBSERVING; octx.running=True
mgr.stop_all(include_observe=True); assert not octx.running
from lineage_auto.winapi import hotkeys as hk
stopf=os.path.join(rroot,'STOP'); open(stopf,'w').close(); reasons=[]
hk.stop_file_path=lambda: stopf; hk._listen_interception_escape=lambda *a: None
ev=hk.start_escape_threads(lambda *a: None, lambda: False, stop_vk=lambda: 0x13, on_stop=reasons.append)
t=time.time()
while os.path.exists(stopf) and time.time()-t<3: time.sleep(0.05)
ev.set(); assert reasons==['STOP file'] and not os.path.exists(stopf), reasons
print('stop: STOP file consumed, observe stopped by stop_all(include_observe) OK')
# HUD numbers on the game PC's 1187x890 window (scaled HUD)
ref=cv2.imread('docs/game_reference/'+sorted(f for f in os.listdir('docs/game_reference') if f.endswith(('.png','.jpg')))[0])
small=cv2.resize(ref,(1187,890),interpolation=cv2.INTER_AREA)
assert hud.read(small)['hp']==hud.read(ref)['hp'] and hud.read(ref)['hp'] is not None, (hud.read(small),hud.read(ref))
print('hud numbers: 1187x890 window reads like 1280x960 OK')
# label_tool boxes -> export_dataset (COCO + YOLO txt), finished frames only
sys.path.insert(0,'tests'); import label_tool as lt, export_dataset as ed
lab_dir=tempfile.mkdtemp(); cv2.imwrite(os.path.join(lab_dir,'f_00001.jpg'),small); cv2.imwrite(os.path.join(lab_dir,'f_00002.jpg'),small)
ld=lt.load_labels(os.path.join(lab_dir,'labels.json'),lab_dir); lt.add_box(ld['images']['f_00001.jpg'],lt.click_box(500,300))
ld['images']['f_00001.jpg']['todo']=False; lt.save_labels(os.path.join(lab_dir,'labels.json'),ld)
exp=tempfile.mkdtemp(); c=ed.export(exp,[lab_dir],val_every=99)
coco=json.load(open(os.path.join(exp,'annotations','instances_train2017.json')))
assert c=={'train':(1,1),'val':(0,0)} and coco['annotations'][0]['bbox']==[478,264,44,72] and coco['annotations'][0]['category_id']==1
yt=open(os.path.join(exp,'labels','train2017',os.path.basename(lab_dir)+'_f_00001.txt')).read().split()
assert yt[0]=='0' and abs(float(yt[1])-500/1187)<1e-3, yt
print('label_tool -> export_dataset COCO/YOLO OK')
# 3 label classes: monster / corpse / player-NPC; only monster boxes feed eval's "monster" points
e3={'monster':[[100,100]],'boxes':[]}
lt.add_box(e3,[80,60,120,130]); lt.add_box(e3,lt.click_box(300,300,lt.DIE),lt.DIE); lt.add_box(e3,lt.click_box(500,300,lt.FIGURE),lt.FIGURE)
assert e3['monster']==[[100,95]] and [lt.box_class(b) for b in e3['boxes']]==[0,2,1] and e3['boxes'][1][:4]==[270,282,330,318]
assert lt.remove_near(e3,300,300) and e3['monster']==[[100,95]] and lt.remove_near(e3,100,95) and e3['monster']==[]
ld['images']['f_00002.jpg']['boxes']=[[10,10,50,50,2],[60,60,90,140,1],[5,5,9,9]]; ld['images']['f_00002.jpg']['todo']=False
lt.save_labels(os.path.join(lab_dir,'labels.json'),ld)
exp2=tempfile.mkdtemp(); ed.export(exp2,[lab_dir],val_every=99)
cats=[a_['category_id'] for a_ in json.load(open(os.path.join(exp2,'annotations','instances_train2017.json')))['annotations']]
assert sorted(cats)==[1,1,2,3], cats                                  # monster, old 4-number box = monster, figure, die
print('label_tool 3 classes -> export category ids OK')
# per-model colour order: shipped models stay RGB, a "bgr" model gets the frame as captured
import dataclasses
seen={}
blob_of=lambda b: seen.__setitem__('b',b) or np.zeros((1,8400,8),np.float32)
px=np.zeros((960,1280,3),np.uint8); px[200:400,400:800]=(255,0,0)   # blue block in BGR (outside blanked HUD)
yolox_mobs.detect_centers(px,640,380,500,infer=blob_of,map_key='dragon_valley')
assert seen['b'][0,2,150,300]==255 and seen['b'][0,0,150,300]==0      # RGB: blue lands in channel 2
orig_get=yolox_mobs.hunt_maps.get
yolox_mobs.hunt_maps.get=lambda k: dataclasses.replace(orig_get(k),channels='bgr')
yolox_mobs.detect_centers(px,640,380,500,infer=blob_of,map_key='dragon_valley')
yolox_mobs.hunt_maps.get=orig_get
assert seen['b'][0,0,150,300]==255 and seen['b'][0,2,150,300]==0      # BGR: blue stays in channel 0
assert all(m.channels=='rgb' for m in hunt_maps.all_maps() if m.key not in ('blessed_orc','fallen_blessed')) and hunt_maps.NEW_MODEL_CHANNELS=='bgr'
assert hunt_maps.get('blessed_orc').channels==hunt_maps.get('fallen_blessed').channels=='bgr'                  # first model trained here (PLAN 0.20)
print('yolox: per-model channel order (shipped rgb, new bgr) OK')
# PLAN 1.6: attack spells. Every catalog role="attack" skill may be auto-cast now (the allow-list only held
# heals / buffs / cure before, so an assigned spell was never pressed), each slot has its own min MP%, range and
# cooldown, and the click order is configurable so the game PC can try all three without a rebuild.
from lineage_auto.skills.policy import is_auto_enabled, use_mechanism
assert is_auto_enabled('386') and use_mechanism('386')['kind']=='target_click'   # 에너지 볼트, role "attack"
assert not is_auto_enabled('999') and is_auto_enabled('383')                     # unknown no, heal still yes
class SpellIn:
    def __init__(s): s.log=[]
    def move(s,x,y): s.log.append('move')
    def click_at(s,x,y): s.log.append('click')
    def press(s,k): s.log.append('press'+k)
    def double_press(s,k): s.log.append('dbl'+k)
    def __getattr__(s,n): return lambda *a,**k: None
sc=TCtx(); sc.character=sc.account.character; sc.can_cast=lambda *a,**k: True
sc.read_mp=lambda r: sc.state.get('mp')
sc.recorder=recmod.Recorder(sc.account,'hunt',rect=sc.rect(),root=rroot)
f5=sc.account.attack('F5'); f5.enabled=True; f5.skill_id='386'
cf=cb.CombatFeature(sc,targeting=FakeTg([(700,400)]*60,[]))
assert cf.active_skills()==['F5'], cf.active_skills()
sc.account.aim_wait_sec=0                 # these cases are about the click order, not about the ellipse wait
for order,want in (('hover_key_click',['move','pressF5','click']),('key_click',['pressF5','click']),
                   ('click_key',['click','pressF5'])):
    sc.account.cast_order=order; sc.input=SpellIn()
    anchor,fired,_h=cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
    assert fired and sc.input.log==want and anchor==(700,400), (order,sc.input.log)
assert cf._spells==3 and sc.recorder.counts['spell_cast']==3, sc.recorder.counts
ev=[json.loads(l) for l in open(os.path.join(sc.recorder.path,'events.jsonl'),encoding='utf-8')]
assert [e['order'] for e in ev]==['hover_key_click','key_click','click_key'], ev
# the three gates: too far, not enough MP, own cooldown -> no spell this beat (the hand attack carries on)
now=time.time(); cf._slot_used={}; cf._skipped={}
f5.range_px=50; assert cf._pick_skill(['F5'],sc.rect(),200.0,now)[0] is None
f5.range_px=0; f5.min_mp=40; sc.state['mp']=10
assert cf._pick_skill(['F5'],sc.rect(),20.0,now)[0] is None
sc.state['mp']=80; assert cf._pick_skill(['F5'],sc.rect(),20.0,now)[0]=='F5'
f5.cooldown=5.0; cf._slot_used['F5']=now
assert cf._pick_skill(['F5'],sc.rect(),20.0,now+1)[0] is None
assert cf._pick_skill(['F5'],sc.rect(),20.0,now+6)[0]=='F5'
assert cf._skipped=={'out_of_range':1,'low_mp':1}, cf._skipped
f5.cooldown=0.0; f5.min_mp=0; cf._slot_used={}; cf._skipped={}; sc.state['mp']=cb.HEAL_MP_RESERVE-1
assert cf._pick_skill(['F5'],sc.rect(),20.0,now)[0] is None and cf._skipped=={'heal_reserve':1}  # heal keeps MP
sc.account.health.use_skill=False; assert cf._pick_skill(['F5'],sc.rect(),20.0,now)[0]=='F5'
sc.account.health.use_skill=True; f5.min_mp=40; f5.cooldown=5.0; cf._slot_used['F5']=now; sc.state['mp']=80
cf._mp_pending=(time.time()-1,'F5',80); sc.state['mp']=74; cf._check_mp_pending(sc.rect())
_mp=[json.loads(l) for l in open(os.path.join(sc.recorder.path,'events.jsonl'),encoding='utf-8') if '"spell_mp"' in l]
assert _mp[-1]['mp_before']==80 and _mp[-1]['mp_after']==74 and cf._mp_pending is None, _mp
sc.state['mp']=80
# the settings survive a save/load round trip (the game PC edits them in the UI, not in the file)
from lineage_auto.config.models import AccountSettings as _AS
back=_AS.from_dict(sc.account.to_dict())
assert back.cast_order=='click_key' and back.attack('F5').min_mp==40 and back.attack('F5').cooldown==5.0
# PLAN 0.34: a slot is (page, key). Page F1 is full, so the spell sits on F2: pressing it switches the page
# first, and the heal that follows is on F1, which switches back. The page key is never pressed twice in a row.
sc.account.cast_order='key_click'
f5.page='F2'
sc.input=SpellIn(); sc.state['hotbar_page']='F1'
cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
sc.press_slot('F1','F5',double=True)                       # the heal right after, as HealthFeature presses it
assert sc.input.log==['pressF2','pressF5','click','pressF1','dblF5'], sc.input.log
sc.input=SpellIn(); cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
assert sc.input.log==['pressF2','pressF5','click'], sc.input.log          # back on F2 -> one switch, not two
sc.input=SpellIn(); cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
assert sc.input.log==['pressF5','click'], sc.input.log                    # already on F2 -> no page key
pg=[json.loads(l) for l in open(os.path.join(sc.recorder.path,'events.jsonl'),encoding='utf-8')
    if '"page_switch"' in l]
assert [(e['from_page'],e['to_page']) for e in pg][:3]==[('F1','F2'),('F2','F1'),('F1','F2')], pg

# PLAN 0.35: the aiming ellipse shows a good second after the slot key on the game PC (v16 waited 0.3 s and
# threw away 144/144 casts). Poll up to account.aim_wait_sec, then click the monster's NEWEST box; no ellipse
# by the deadline = click anyway, because a click on a monster with no spell armed is only a hand attack.
# PLAN 0.39: the ellipse must come AFTER the key (233615: 94/94 read at 0.0 s = a picture already there)
Cur.classify=lambda s,h,md5=None: 'cast' if s.aim and h=='ell' else 'unknown'
sc.cursors.cast_registered=True; sc.cursors.aim=True
_pressed=[]
class SpellIn(SpellIn):
    def press(s,k): s.log.append('press'+k); _pressed.append(k)
cb.CursorProbe.current_hash=staticmethod(lambda: 'ell' if _pressed else 'ground')
sc.account.aim_wait_sec=0.5
sc.state['hotbar_page']='F2'
_pressed.clear(); sc.input=SpellIn(); cf.targeting=FakeTg([(730,430)],[])
t0=time.time(); anchor,fired,hold=cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
assert fired and sc.input.log==['pressF5','click'] and anchor==(730,430), (sc.input.log,anchor)
assert time.time()-t0<0.4, 'the ellipse was up at once: no need to wait out aim_wait_sec'
assert hold==sc.rect().to_screen(730,430), hold      # PLAN 0.39: the box centre, not 25 px below it (ground)
# the ellipse was already up before the key: not this key's -> wait out aim_wait_sec (logged as no ellipse)
_pressed.append('x'); sc.input=SpellIn(); cf.targeting=FakeTg([(730,430)],[])
t0=time.time(); _a,fired,_h=cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
assert fired and time.time()-t0>=sc.account.aim_wait_sec, time.time()-t0
_ev=[json.loads(l) for l in open(os.path.join(sc.recorder.path,'events.jsonl'),encoding='utf-8') if '"spell_cast"' in l]
assert _ev[-1]['aim_delay_s'] is None and _ev[-1]['cursor_before_key']=='ell', _ev[-1]
_pressed.clear()
# no ellipse at all -> waits the whole aim_wait_sec, then clicks the newest box anyway
sc.cursors.aim=False
sc.input=SpellIn(); cf.targeting=FakeTg([(730,430)],[])
t0=time.time(); _a,fired,_h=cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
assert fired and sc.input.log==['pressF5','click'], sc.input.log
assert sc.account.aim_wait_sec <= time.time()-t0 < sc.account.aim_wait_sec+0.4, time.time()-t0
assert not sc.state.get('skill_pause_until'), sc.state      # no self-inflicted spell pause any more
# the lock died while the spell armed: throw it at the nearest neighbour instead
sc.cursors.aim=True
nb=FakeTg([None],[]); nb.last_monsters=[(900,500),(700,420),(645,381)]   # 645,381 is the character's own box (< SELF_R)
_pressed.clear(); sc.input=SpellIn(); cf.targeting=nb
_a,fired,_h=cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
assert fired and _a==(700,420) and sc.input.log==['pressF5','click'], (_a,sc.input.log)
# nothing left at all: right-click cancels the armed spell (ESC is the bot's stop hotkey, never usable here)
class RIn(SpellIn):
    def click_right(s): s.log.append('rclick')
_pressed.clear(); sc.input=RIn(); cf.targeting=FakeTg([None],[])
_a,fired,_h=cf._cast_at_target('F5',sc.rect(),(640,380),(700,400))
assert not fired and sc.input.log==['pressF5','rclick'], sc.input.log
ev=[json.loads(l) for l in open(os.path.join(sc.recorder.path,'events.jsonl'),encoding='utf-8')
    if '"spell_cast"' in l]
assert [e['ok'] for e in ev[-4:]]==[True,True,True,False], [e['ok'] for e in ev[-4:]]
assert ev[-1]['reason']=='no_target_left' and ev[-5]['aim_delay_s'] is not None, ev[-1]
assert ev[-3]['aim_delay_s'] is None, ev[-3]          # the deadline run records no delay
reads=ev[-5]['cursor_after_key']
assert reads and all('hash' in r and 'md5' in r and 'kind' in r and 'at' in r for r in reads), reads
sc.account.aim_wait_sec=1.8
# PLAN 0.35: 3 chat failures = the spell armed and nobody clicked in time -> try the other click order
tf2=tg.TargetingFeature(sc)
sc.input.last_key=('F5',time.monotonic())
sc.account.cast_order='key_click'
for n in range(tg.SPELL_FAIL_STRIKES):
    tf2._magic_fail()
assert sc.account.cast_order=='hover_key_click' and sc.state['spell_fail_strikes']==0, sc.state
fail=[json.loads(l) for l in open(os.path.join(sc.recorder.path,'events.jsonl'),encoding='utf-8')
      if '"spell_fail_chat"' in l]
assert len(fail)==tg.SPELL_FAIL_STRIKES and fail[-1]['switched_to']=='hover_key_click', fail[-1]
sc.account.cast_order='key_click'; sc.state.pop('skill_pause_until',None)
# the aim wait survives a save / load round trip (the game PC tunes it in the UI)
assert _AS.from_dict(sc.account.to_dict()).aim_wait_sec==1.8
# PLAN 0.36: the Cursor tab only warns about pictures <= 2 bits apart (corpse/npc 4 apart are both right);
# an ellipse wrongly registered as attack is still read as cast
from lineage_auto.runtime.cursor_profile import CursorProfile as _CP
prof=_CP({'attack':'fc92fe3800000000','cast':'fcfefe3800000000'})
assert prof.near_duplicates()==[] and prof.classify('fc92fe3800000000','')=='cast'
assert _CP({'corpse':'f0f0f03800000000','npc':'f0f0602000000000'}).near_duplicates()==[]
assert _CP({'corpse':'f0f0f03800000000','npc':'f0f0f03800000003'}).near_duplicates()==[('corpse','npc',2)]
print('attack spells: 3 orders, pages, 1.8s ellipse wait, newest box / neighbour / cancel OK')
# PLAN 0.31: YOLOX on its own thread; targeting reads the newest result, never the character's own box
from lineage_auto.runtime.detector import DetectorThread
importlib.reload(tg)  # the scan tests above replaced tg.detect_centers / CursorProbe
dframe=cv2.imread('records_game/20261125_092741_hunt/f_00007.jpg')   # 1280x960, the v15 night hunt
if dframe is not None:
    dctx2=TCtx(); dctx2.account.hunt_map='blessed_orc'
    dctx2.rect=lambda: ClientRect(0,0,1280,960); dctx2.char_pos=lambda r: (640,380)
    dctx2.grabber=types.SimpleNamespace(grab_bgr=lambda r: dframe, close_thread=lambda: None)
    det=DetectorThread(dctx2)
    assert det.size==640 and not det.roi and det.fps=={'search':2,'fight':2}, det.describe()
    assert det.threads=={'search':2,'fight':1}, det.threads           # PLAN 0.34: 2 threads only while searching
    assert det.adaptive and det.fight_size==416                       # PLAN 0.33: every 2nd fight detect is cheap
    assert det._mode(0)==(640,False,2,'search') and det._mode(1)==(640,False,2,'search')
    dctx2.state['fight_until']=time.monotonic()+1
    assert det._mode(0)==(640,False,1,'fight') and det._mode(1)==(416,True,1,'fight'), (det._mode(0),det._mode(1))
    dctx2.state['fight_until']=0
    det.start(); first=det.newest(0,wait=5.0); second=det.newest(first.seq,wait=5.0)
    assert first and second.seq>first.seq and first.hits, (first, second)
    tf2=tg.TargetingFeature(dctx2); tf2.detector=det
    pts,_=tf2.candidates(dctx2.rect(),(640,380))
    assert pts and all(math.hypot(x-640,y-380)>tg.SELF_R for x,y in tf2.last_monsters), tf2.last_monsters
    det.stop(); assert not det._thread.is_alive()
    det._step_down(60); assert det.size==640                     # fast enough on the first log: kept for good
    det._stepped=False; det._step_down(95); assert det.size==640      # 95 ms still keeps 2/s: no step down
    det._stepped=False; det._step_down(600); assert det.size==416     # cannot keep 2/s: one step down
    det.fps['search']=5; det._slow_down('search',180,5)               # PLAN 0.33: 180 ms x 5/s -> one step down
    assert det.fps['search']==4 and det._slow_down('search',10,1)<0.03 and det.fps['search']==4
    for _ in range(5): det._slow_down('search',300,2)                 # PLAN 0.34: searching never goes under 2/s
    assert det.fps['search']==2, det.fps
    for _ in range(5): det._slow_down('fight',300,2)                  # a fight may go down to 1/s
    assert det.fps['fight']==1, det.fps
    print(f'detector thread: {det.describe()}, {first.ms:.0f} ms, hits {first.hits[:3]} OK')
# PLAN 0.39: walks avoid ground left 8-90 s ago; HP falling + a box next to us = hit back; idle gaps are measured
from lineage_auto.features import exploration as exm
_r={i:parts for _s,i,parts in exm.score_directions((0,0),100.0,[],[(16,0,50.0)],None,lambda i:True,None,16)}
_e=exm.WALK_DIRECTIONS.index((1,0)); _w=exm.WALK_DIRECTIONS.index((-1,0))
assert _r[_e]['back'] and not _r[_w]['back'], _r
_r={i:parts for _s,i,parts in exm.score_directions((0,0),100.0,[],[(16,0,97.0)],None,lambda i:True,None,16)}
assert not _r[_e]['back']                                      # just walked through: not "going back"
_evs=[]
_st=types.SimpleNamespace(ctx=types.SimpleNamespace(state={'hp_abs':(100,200)},log=lambda m:None,recorder=None,
                          input=types.SimpleNamespace(last_action_t=None)),_hp_prev=None,_idle_open=None,
                          targeting=types.SimpleNamespace(last_monsters=[(690,380),(900,380)]))
_probed=[]; _cursor_ok=[True]
def _probe(points,rect):  # the hover: an attack cursor there or nothing (another player is never hit)
    _probed.append(points); return tg.Target(*points[0],*rect.to_screen(*points[0])) if _cursor_ok[0] else None
_st.targeting.probe=_probe
_st._nearest_box=lambda c: AccountSession._nearest_box(_st,c)
assert not AccountSession._hp_falling(_st); _st.ctx.state['hp_abs']=(90,200); assert AccountSession._hp_falling(_st)
_t=AccountSession._defend(_st,ClientRect(0,0,1280,960),(640,380),True); assert _t.local==(690,380) and _probed==[[(690,380)]], _t
_cursor_ok[0]=False; assert AccountSession._defend(_st,ClientRect(0,0,1280,960),(640,380),True) is None  # no attack cursor
_cursor_ok[0]=True
assert AccountSession._defend(_st,ClientRect(0,0,1280,960),(640,380),False) is None
_st.targeting.last_monsters=[(900,380)]; assert AccountSession._defend(_st,ClientRect(0,0,1280,960),(640,380),True) is None
_st.targeting.last_monsters=[(690,380)]
_st.ctx.recorder=types.SimpleNamespace(count=lambda *a:None,timing=lambda *a:None,event=lambda k,**d:_evs.append((k,d)))
_st.ctx.input.last_action_t=time.monotonic()-2; AccountSession._idle_watch(_st,(640,380),False)
assert _st._idle_open is not None and not _evs
_st.ctx.input.last_action_t=time.monotonic(); AccountSession._idle_watch(_st,(640,380),False)
assert _evs and _evs[0][0]=='idle_gap' and _evs[0][1]['seconds']>=1.9 and _st._idle_open is None, _evs
print('0.39: no walking back / hit back when HP falls / idle gaps OK')
# PLAN 0.40: danger = HP burst or a crowd next to us -> heal at once, step back, town while HP is still high
class DIn(In):
    def __init__(s): super().__init__(); s.clicks=[]
    def click_at(s,x,y): s.clicks.append((x,y))
class DCtx(Ctx):
    def __init__(s,acc,hp): super().__init__(acc,hp); s.input=DIn(); s.recorder=None
    def char_pos(s,r): return (640,380)
    def rect(s): return ClientRect(0,0,1280,960)
acc_d=AccountSettings(); acc_d.hunt_map='fallen_blessed'   # the crowd rule only runs on an mp_hungry ground
cd=DCtx(acc_d,100); hd=HealthFeature(cd)
assert hd.tick(cd.rect())==100 and not hd.danger and not cd.input.log
cd.hp_reader.v=75                                                  # -25 % inside DANGER_WINDOW
assert hd.tick(cd.rect())==75 and hd.danger and cd.input.log==[('dbl','F5')], cd.input.log
cd.state['mobs_near']=[(700,380),(690,420),(690,340)]              # the crowd alone is danger too
cd.hp_reader.v=100; hd._hp_log=[]; hd._danger_until=0.0
assert hd.tick(cd.rect())==100 and hd.danger and len(cd.input.clicks)==1, cd.input.clicks
assert cd.input.clicks[0][0]<640 and cd.input.log==[('dbl','F5')], cd.input.clicks  # away, no heal at full HP
hd.tick(cd.rect()); assert len(cd.input.clicks)==1                                  # one step per cooldown
hd._last_retreat=0.0; cd.state['fight_until']=time.monotonic()+5
hd.tick(cd.rect()); assert len(cd.input.clicks)==1                 # never while a fight holds the mouse
# PLAN 0.40 (user 26/11): at 오크의 땅 the crowd alone is not danger - only the HP burst (keep v20's 5.25 kills/min)
cd.state.pop('fight_until'); hd._last_retreat=0.0; hd._danger_until=0.0; acc_d.hunt_map='blessed_orc'
assert hd.tick(cd.rect())==100 and not hd.danger and len(cd.input.clicks)==1, cd.input.clicks
acc_t=AccountSettings(); acc_t.health.return_town=True; acc_t.health.use_potion=False
ct=DCtx(acc_t,100); ct.can_cast=lambda i,r=None: False; ht=HealthFeature(ct)   # MP gone, no potion
ht.tick(ct.rect()); ct.hp_reader.v=75
assert ht.tick(ct.rect())==75 and ht.returned and ct.input.log==[('press','F8')], ct.input.log
print('0.40: danger heal / step back / early town OK')
print('ALL SMOKE TESTS PASSED')
