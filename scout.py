import anthropic
import argparse
import json
import re
import smtplib
import os
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a talent scout for CapitalG, Google's growth equity fund.
Find technical leaders at large F1000 companies who have spoken publicly in the last 30 days.

INCLUDE only people matching ALL of these:
- Title is VP, SVP, Head of, or Chief Data / AI / Technology Officer
- Works at an F1000 company with over $1 billion in revenue
- Has spoken at a conference, appeared on a podcast, or been quoted in the press recently
- NOT from financial services, banking, insurance, or healthcare

PRIORITIZE these verticals:
- Energy and utilities
- Telecom and media
- Automotive and manufacturing
- Logistics and supply chain
- Aerospace and defense
- Retail and consumer

For each person, note any Google connection such as Google Cloud customer,
Google Cloud Next speaker, Vertex AI or BigQuery partnership.
If none found write: None found.

Return ONLY a JSON array. Your entire response must be valid JSON.
Start with [ and end with ]. No text before or after. No markdown fences.

[
  {
    "name": "Jane Smith",
    "title": "SVP of Data",
    "company": "Ford Motor Company",
    "vertical": "Automotive",
    "google_tie": "Ford announced Vertex AI partnership 2025",
    "signal": "Spoke at NVIDIA GTC March 2026"
  }
]"""

SEARCHES = [
    "VP SVP CDO CTO engineering data AI energy telecom automotive conference speaker 2026",
    "NVIDIA GTC Google Cloud Next HumanX Databricks VP SVP enterprise speaker 2026",
    "Technovation podcast SVP VP CDO CTO enterprise F1000 interview 2026",
    "Data Chief podcast VP SVP CDO enterprise interview 2026",
    "CES 2026 enterprise CTO CDO VP technology keynote industrial manufacturing",
    "CERAWeek energy technology leader VP SVP speaker 2026",
    "automotive manufacturing conference VP engineering data AI speaker 2026",
    "logistics supply chain conference technology leader VP SVP 2026",
    "telecom media conference VP SVP engineering data AI speaker 2026",
    "Google Cloud Next 2026 customer session VP SVP director enterprise speaker",
    "enterprise VP SVP CDO AI blog post published interview quoted 2026",
    "AI 75 OR AI 100 VP SVP director enterprise F1000 honoree 2026",
]


def run_scout(days=30):
    client = anthropic.Anthropic()

    prompt = f"""Search for F1000 technical leaders with a public signal in the last {days} days.

Use all of these searches:
{chr(10).join(f"{i+1}. {q}" for i, q in enumerate(SEARCHES))}

Return 10 to 15 people as a JSON array.
Your entire response must be only the JSON array, starting with [ and ending with ].
No preamble. No explanation. No markdown."""

    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 15}]

    print(f"CapitalG Scout — searching last {days} days")
    print("-" * 40)

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            raw = " ".join(
                block.text for block in response.content
                if hasattr(block, "text")
            ).strip()

            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1 and end > start:
                json_str = raw[start:end + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    people = []
                    for match in re.finditer(r'\{[^{}]+\}', json_str, re.DOTALL):
                        try:
                            people.append(json.loads(match.group()))
                        except json.JSONDecodeError:
                            continue
                    if people:
                        return people

            print("No results parsed.")
            return []

        elif response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    q = getattr(block, "input", {}).get("query", "...")
                    print(f"  Searching: {q}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "",
                    })
            messages.append({"role": "user", "content": tool_results})

        else:
            raise RuntimeError(f"Unexpected stop_reason: {response.stop_reason}")


def format_html(people):
    today = date.today().strftime("%B %d, %Y")

    rows = ""
    for p in people:
        google = p.get("google_tie", "None found")
        google_bg = "#e6f4ea" if google.lower() != "none found" else "#ffffff"
        rows += f"""<tr>
<td style="padding:12px 16px;border-bottom:1px solid #e0e0e0;font-weight:600;white-space:nowrap;">{p.get("name","")}</td>
<td style="padding:12px 16px;border-bottom:1px solid #e0e0e0;">{p.get("title","")}</td>
<td style="padding:12px 16px;border-bottom:1px solid #e0e0e0;white-space:nowrap;">{p.get("company","")}</td>
<td style="padding:12px 16px;border-bottom:1px solid #e0e0e0;">{p.get("vertical","")}</td>
<td style="padding:12px 16px;border-bottom:1px solid #e0e0e0;background:{google_bg};">{google}</td>
<td style="padding:12px 16px;border-bottom:1px solid #e0e0e0;">{p.get("signal","")}</td>
</tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<div style="max-width:960px;margin:24px auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

  <div style="background:#1a73e8;padding:24px 32px;">
    <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:600;">CapitalG Scout</h1>
    <p style="margin:6px 0 0;color:#e8f0fe;font-size:14px;">{today} &nbsp;&middot;&nbsp; {len(people)} targets this week</p>
  </div>

  <div style="padding:24px 32px;overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;font-size:14px;color:#333;">
      <thead>
        <tr style="background:#f8f9fa;">
          <th style="padding:12px 16px;text-align:left;border-bottom:2px solid #e0e0e0;white-space:nowrap;">Name</th>
          <th style="padding:12px 16px;text-align:left;border-bottom:2px solid #e0e0e0;">Title</th>
          <th style="padding:12px 16px;text-align:left;border-bottom:2px solid #e0e0e0;">Company</th>
          <th style="padding:12px 16px;text-align:left;border-bottom:2px solid #e0e0e0;">Vertical</th>
          <th style="padding:12px 16px;text-align:left;border-bottom:2px solid #e0e0e0;">Google Tie</th>
          <th style="padding:12px 16px;text-align:left;border-bottom:2px solid #e0e0e0;">Signal</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <div style="padding:16px 32px;border-top:1px solid #e0e0e0;background:#f8f9fa;">
    <p style="margin:0;color:#999;font-size:12px;">Sent automatically every Sunday by CapitalG Scout.</p>
  </div>

</div>
</body>
</html>"""


def send_email(html, gmail_user, gmail_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"CapitalG Scout — Weekly Report"
    msg["From"] = f"CapitalG Scout <{gmail_user}>"
    msg["To"] = gmail_user
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, gmail_user, msg.as_string())
    print("Email sent successfully.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", "-d", type=int, default=30)
    args = parser.parse_args()

    people = run_scout(days=args.days)
    html = format_html(people)

    print(f"\n{len(people)} targets found.")
    for i, p in enumerate(people, 1):
        print(f"  {i:02d}. {p.get('name')} — {p.get('title')} at {p.get('company')}")

    # Send email directly via Gmail SMTP
    gmail_user = os.environ.get("GMAIL_USERNAME")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if gmail_user and gmail_password:
        send_email(html, gmail_user, gmail_password)
    else:
        print("No email credentials found — saving report.html instead.")
        with open("report.html", "w") as f:
            f.write(html)


if __name__ == "__main__":
    main()
