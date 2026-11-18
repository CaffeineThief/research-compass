"""Offline workflow comparison; synthetic responses, no LLM or network benchmark."""
import copy
import hashlib
import json
import time
from pathlib import Path
from test_workflow import complete
from researchlib.budget import reserve_search, record_search
from researchlib.evaluation import evaluate, record_review
from researchlib.output import validate


def benchmark():
    initial = complete()
    base = initial['candidates'][0]
    initial['candidates'] = []
    for i in range(6):
        c = copy.deepcopy(base); c['id'] = f'TEST-C{i + 1}'
        if i >= 3:
            c['gates']['data'].update(status='fail', reason='TEST confirmed unavailable dataset')
        initial['candidates'].append(c)
    initial['report']['selected_candidate_ids'] = ['TEST-C1', 'TEST-C2', 'TEST-C3']
    digest = hashlib.sha256(json.dumps(initial, sort_keys=True).encode()).hexdigest()
    results = {}
    for mode in ('all_detailed', 'screen_then_detail'):
        s = copy.deepcopy(initial); start = time.perf_counter(); detailed = []
        for c in s['candidates']:
            if mode == 'screen_then_detail':
                record_review(s, c['id'], {'stage': 'screening', 'reason': 'TEST screen known gates', 'main_blocker': c['gates']['data']['reason'], 'next_actions': ['TEST assess gate']})
                if evaluate(c, s)['status'] == 'rejected':
                    record_review(s, c['id'], {'stage': 'hold', 'reason': 'TEST failed access gate', 'main_blocker': 'TEST dataset unavailable', 'next_actions': ['TEST reopen if access changes']})
                    continue
                record_review(s, c['id'], {'stage': 'detailed', 'reason': 'TEST gates support further review', 'next_actions': []})
            entry = reserve_search(s, 'TEST nearest study ' + c['id'], 'novelty', 'offline-fixture', 1)
            record_search(s, entry['id'], {'results': [{'paper_id': 'TEST-P1'}]})
            c['novelty']['search_ids'] = [entry['id']]
            c['stages'] = dict.fromkeys(s['stages'], 'complete')
            detailed.append(c['id'])
        errors = validate(s, final=True)
        selected = [c for c in s['candidates'] if c['id'] in s['report']['selected_candidate_ids']]
        results[mode] = {'input_sha256': digest, 'max_requests': s['config']['max_requests'], 'max_results': s['config']['max_results'],
                         'requests': s['usage']['requests'], 'elapsed_seconds': round(time.perf_counter() - start, 6),
                         'detailed_candidates': detailed, 'selected_core_evidence_ids': sorted({p for c in selected for p in c['paper_ids']}),
                         'selected_missing_fields': errors, 'tokens': None}
    assert results['all_detailed']['requests'] == 6
    assert results['screen_then_detail']['requests'] == 3
    assert all(not result['selected_missing_fields'] for result in results.values())
    assert results['all_detailed']['selected_core_evidence_ids'] == results['screen_then_detail']['selected_core_evidence_ids']
    return {'test_data': True, 'scope': 'Fixed synthetic candidates and responses; measured local bookkeeping only. No LLM, actual literature retrieval, GPU or token measurements; elapsed time is not a research speed estimate.', 'results': results}


if __name__ == '__main__':
    import sys
    output = json.dumps(benchmark(), ensure_ascii=False, indent=2) + '\n'
    if len(sys.argv) > 1: Path(sys.argv[1]).write_text(output)
    else: print(output, end='')
