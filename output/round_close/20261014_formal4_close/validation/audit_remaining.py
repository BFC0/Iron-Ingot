"""Run existing validators once each remaining market's source group is available."""
import json
import subprocess
import time
from pathlib import Path

BASE=Path(__file__).parent
PANELS=['productionenvironmental','productionhr','logisticsemissions','marketdetails','productiondetails','market','production','logistics','incomestatement','balancesheet','cashflow','societalimpact']
assert len(set(PANELS))==12
pending=set(range(1,9))
print('Waiting for full source groups: markets 1-8',flush=True)
while pending:
    for market in sorted(pending,reverse=True):
        if not all((BASE.parent/'raw'/f'market{market}_formal4_{panel}.json').is_file() for panel in PANELS):
            continue
        for script in ['validate_market.py','pair_results_svg.py']:
            result=subprocess.run(['python',str(BASE/script),'--market',str(market)],capture_output=True,text=True,check=True)
            info=json.loads(result.stdout)
            print(json.dumps(dict(market=market,script=script,output=info['output'],fields=info.get('field_status_counts'),charts=info.get('counts',info.get('sequence_status_counts'))),ensure_ascii=False),flush=True)
        pending.remove(market)
    if pending:
        time.sleep(15)
