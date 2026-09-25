from precompute_team_four_factors_v2 import *

if __name__ == '__main__':
    try:
        cache=json.loads(CACHE.read_text(encoding='utf-8'))
    except Exception:
        cache={}
    seasons=cache.get('seasons') if isinstance(cache.get('seasons'),dict) else {}
    completed=cache.get('completed') if isinstance(cache.get('completed'),list) else []
    cache={'version':4,'seasons':seasons,'completed':sorted(set(completed))}
    n=import_existing_bref_html(cache)
    print('Recovered',n,'Four Factors season maps from existing local BRef HTML.')
    print('Cache:',CACHE)
    print('Completed:',len(cache['completed']))
