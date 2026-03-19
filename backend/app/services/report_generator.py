import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
from datetime import datetime
import pytz

template_dir = os.path.dirname(os.path.abspath(__file__))
env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=select_autoescape(['html', 'xml'])
)


def get_ist_datetime():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    return now.strftime("%d/%m/%Y, %I:%M:%S %p IST")


def create_pdf_from_analysis(analysis_data: dict, filename: str, analysis_type: str = "full") -> bytes:
    risks = analysis_data.get('risks', [])
    high_risks = [r for r in risks if str(r.get('severity', '')).lower() == 'high']
    medium_risks = [r for r in risks if str(r.get('severity', '')).lower() == 'medium']
    low_risks = [r for r in risks if str(r.get('severity', '')).lower() == 'low']

    high_count = len(high_risks)
    medium_count = len(medium_risks)
    low_count = len(low_risks)
    total_risks = high_count + medium_count + low_count

    # Use the AI-determined overall_risk_score (0-100)
    danger_score_pct = analysis_data.get('overall_risk_score', 50)
    if not isinstance(danger_score_pct, (int, float)):
        danger_score_pct = 50
    danger_score_pct = max(0, min(100, danger_score_pct))

    if danger_score_pct <= 30:
        bar_color = '#16a34a'
    elif danger_score_pct <= 60:
        bar_color = '#d97706'
    else:
        bar_color = '#dc2626'

    top_clauses = [
        {
            "clause": c.get('clause_title', 'Untitled'),
            "text": c.get('clause_text', ''),
            "explanation": c.get('plain_english', ''),
            "importance": c.get('importance', 'standard'),
        } for c in analysis_data.get('key_clauses', [])
    ]

    risks_nested = {
        "counts": {"High": high_count, "Medium": medium_count, "Low": low_count},
        "top_clauses": {
            "High": ["{}: {}".format(r.get('risk_title', ''), r.get('description', '')) for r in high_risks],
            "Medium": ["{}: {}".format(r.get('risk_title', ''), r.get('description', '')) for r in medium_risks],
            "Low": ["{}: {}".format(r.get('risk_title', ''), r.get('description', '')) for r in low_risks],
        }
    }

    parties = analysis_data.get('parties', [])
    party_str = []
    for p in parties:
        if isinstance(p, dict):
            party_str.append("{}: {}".format(p.get('role', 'Party'), p.get('name', 'Unknown')))
        elif isinstance(p, str):
            party_str.append(p)

    template_name = 'template_short.html' if analysis_type == 'short' else 'template.html'
    template = env.get_template(template_name)

    # Flatten obligations to strings
    raw_obligations = analysis_data.get('obligations', [])
    obligations = []
    for ob in raw_obligations:
        if isinstance(ob, dict):
            obligations.append(ob.get('description', str(ob)))
        elif isinstance(ob, str):
            obligations.append(ob)

    missing_clauses = analysis_data.get('missing_clauses', [])

    context = {
        "current_ist_time": get_ist_datetime(),
        "doc_id": filename,
        "summary_text": analysis_data.get('summary', 'No summary provided.'),
        "document_type": analysis_data.get('document_type', 'Legal Document'),
        "overall_risk_score": analysis_data.get('overall_risk_score', 0),
        "key_terms": [c.get('clause_title', '') for c in analysis_data.get('key_clauses', []) if c.get('clause_title')],
        "parties": party_str,
        "top_clauses": top_clauses,
        "risks": risks_nested,
        "obligations": obligations,
        "missing_clauses": missing_clauses,
        "danger_score_pct": round(danger_score_pct),
        "bar_color": bar_color,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "total_risks": total_risks,
    }

    html_string = template.render(context)
    return HTML(string=html_string).write_pdf()
