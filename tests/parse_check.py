from pathlib import Path
import sys
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app.ai import agent

texts = [
    "I mainly follow Nvidia, AMD and TSMC.",
    "I'm particularly interested in AI infrastructure.",
    "I follow Nvidia and AMD, but I'm also interested in semiconductor manufacturing.",
]

for t in texts:
    print('TEXT:', t)
    print('companies:', agent.parse_companies_from_text(t))
    print('interests:', agent.parse_interests_from_text(t))
    print('role:', agent.parse_role_from_text(t))
    print('---')
