#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""User-started classic bridge, independent of Steam's launch mechanism."""
import argparse,datetime,json,pathlib,subprocess,time,math
from classic_game import ROOT,sha,validate_motor_profile,rollback
from classic_log_summary import summarize

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','uninstall']);p.add_argument('--session',type=pathlib.Path,required=True);p.add_argument('--candidate-all-effects',action='store_true');p.add_argument('--strength',type=float,default=0.25);a=p.parse_args();out=a.session.resolve();state=json.loads((out/'classic-session.json').read_text())
 if not math.isfinite(a.strength) or not 0<a.strength<=1:p.error('strength must be finite in (0,1]')
 if not a.candidate_all_effects and a.strength!=0.25:p.error('Gain changes are explicit candidate-only tests')
 if state.get('purpose')!='g923-temporary-classic-game-test' or state.get('project')!=str(ROOT):raise SystemExit('Invalid installation manifest')
 stop=out/'manual-stop'
 if a.action=='stop':stop.touch();print('Запрошена остановка моста.');return
 if a.action=='uninstall':
  stop.touch();rollback(out,state);print('Наша DLL удалена/исходная восстановлена. Сначала закройте игру перед следующим запуском.');return
 target=pathlib.Path(state['target'])
 if not target.is_file() or sha(target)!=state['installed_sha']:raise SystemExit('Установленная DLL изменилась; запуск отменён')
 profile=json.loads(pathlib.Path(state['motor_profile']).read_text());sign=validate_motor_profile(profile)
 # A new manual start explicitly acknowledges a previous stop request.
 stop.unlink(missing_ok=True)
 logs=out/('manual-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));logs.mkdir(exist_ok=False)
 logpath=logs/'native.jsonl';binary=ROOT/('build/crossover-base/G923ClassicLab-all-effects-candidate' if a.candidate_all_effects else 'build/crossover-base/swift/debug/G923ClassicLab')
 extra=['--all-effects','--strength',str(a.strength)] if a.candidate_all_effects else []
 print(('Кандидат: все обычные FFB-эффекты, сила '+str(round(a.strength*100))+'%; TRUEFORCE выключен.' if a.candidate_all_effects else 'Обычный FFB: 25%, измеренный знак мотора; TRUEFORCE и эффекты трения выключены.')+'\nРуль может двигаться. Запустите игру самостоятельно из Steam.\nОстановка: кнопка Stop или Ctrl-C в этом окне. Логи: '+str(logs),flush=True)
 child=None;timedout=False
 with logpath.open('w') as log:
  child=subprocess.Popen([str(binary),'--map',state['mapping'],'--user-ready','--motor-sign',str(int(sign)),*extra],stdout=log,stderr=subprocess.STDOUT)
  try:
   while child.poll() is None:
    if stop.exists():break
    time.sleep(.1)
  except KeyboardInterrupt:pass
  finally:
   if child.poll() is None:
    child.terminate()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:child.kill();child.wait();timedout=True
 with logpath.open(errors='replace') as log:summary=summarize(log)
 summary['shutdown_timeout']=timedout;(logs/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('Мост остановлен. Финальный Stop: '+str(summary['final_force_command_is_successful_stop'])+'; ошибки HID: '+str(summary['hid_output_errors']),flush=True)
 print('DLL остаётся установленной. Для её удаления используйте Uninstall.');return child.returncode
if __name__=='__main__':raise SystemExit(main())
