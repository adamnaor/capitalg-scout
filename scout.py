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

For each person, research and note their company's Google connection. This includes Google Cloud, Workspace, Vertex AI, BigQuery, Google Maps, Android Enterprise, YouTube, data center energy deals, or any Google partnership. Every major F1000 company uses at least one Google product — find it.

 such as Google Cloud customer,
Google Cloud Next speaker, Vertex AI or BigQuery partnership.
You must find a Google connection for every person. Every large F1000 company has some relationship with Google — search for Google Cloud usage, Workspace adoption, Android Enterprise, Google Maps Platform, YouTube advertising, data center partnerships, or any Google product. Be thorough. Only write "None confirmed" if after searching you truly find zero evidence of any Google product or partnership.
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

    # Group people by vertical
    verticals = {}
    for p in people:
        v = p.get("vertical", "Other")
        verticals.setdefault(v, []).append(p)

    # Count google ties
    google_tie_count = sum(
        1 for p in people
        if p.get("google_tie", "").lower() != "none found"
    )

    # Build stat cards
    stats_html = f"""
    <td style="width:33%;padding:0 8px;">
      <div style="background:#f9f9f9;border-radius:12px;padding:20px 24px;">
        <div style="font-size:32px;font-weight:700;color:#000;letter-spacing:-1px;">{len(people)}</div>
        <div style="font-size:13px;color:#888;margin-top:4px;font-weight:500;">Targets this week</div>
      </div>
    </td>
    <td style="width:33%;padding:0 8px;">
      <div style="background:#f9f9f9;border-radius:12px;padding:20px 24px;">
        <div style="font-size:32px;font-weight:700;color:#000;letter-spacing:-1px;">{len(verticals)}</div>
        <div style="font-size:13px;color:#888;margin-top:4px;font-weight:500;">Verticals covered</div>
      </div>
    </td>
    <td style="width:33%;padding:0 8px;">
      <div style="background:#f9f9f9;border-radius:12px;padding:20px 24px;">
        <div style="font-size:32px;font-weight:700;color:#000;letter-spacing:-1px;">{google_tie_count}</div>
        <div style="font-size:13px;color:#888;margin-top:4px;font-weight:500;">Existing Google ties</div>
      </div>
    </td>
    """

    # Build vertical sections
    sections_html = ""
    for vertical, members in verticals.items():
        rows = ""
        for p in members:
            google = p.get("google_tie", "None found")
            has_tie = google.lower() != "none found"

            google_html = f"""
                <div style="font-size:11px;font-weight:600;color:#1a73e8;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">GOOGLE TIE</div>
                <div style="font-size:13px;color:{'#333' if has_tie else '#aaa'};">{google}</div>
            """ if has_tie else f"""
                <div style="font-size:11px;font-weight:600;color:#aaa;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">GOOGLE TIE</div>
                <div style="font-size:13px;color:#aaa;">None found</div>
            """

            signal = p.get("signal", "")
            # Try to extract a source name from the signal (before first period or comma)
            signal_parts = signal.split(" discussing ") if " discussing " in signal else [signal, ""]
            signal_source = signal_parts[0].strip() if signal_parts else signal
            signal_detail = signal_parts[1].strip() if len(signal_parts) > 1 else ""

            rows += f"""
            <tr>
              <td style="padding:20px 24px;border-bottom:1px solid #f0f0f0;vertical-align:top;width:28%;">
                <div style="font-size:15px;font-weight:600;color:#000;margin-bottom:3px;">{p.get("name","")}</div>
                <div style="font-size:13px;color:#555;margin-bottom:3px;">{p.get("title","")}</div>
                <div style="font-size:13px;font-weight:500;color:#000;">{p.get("company","")}</div>
                <div style="display:inline-block;margin-top:8px;padding:3px 10px;background:#f0f0f0;border-radius:20px;font-size:11px;color:#666;font-weight:500;">{p.get("vertical","")}</div>
              </td>
              <td style="padding:20px 24px;border-bottom:1px solid #f0f0f0;vertical-align:top;width:30%;">
                {google_html}
              </td>
              <td style="padding:20px 24px;border-bottom:1px solid #f0f0f0;vertical-align:top;width:42%;">
                <div style="font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">SIGNAL</div>
                <div style="font-size:13px;color:#1a73e8;font-weight:500;margin-bottom:4px;">{signal_source}</div>
                {"<div style='font-size:13px;color:#444;line-height:1.5;'>" + signal_detail + "</div>" if signal_detail else "<div style='font-size:13px;color:#444;line-height:1.5;'>" + signal + "</div>"}
              </td>
            </tr>"""

        sections_html += f"""
        <div style="margin-bottom:32px;">
          <div style="padding:0 0 12px 0;margin-bottom:0;border-bottom:2px solid #000;">
            <span style="font-size:17px;font-weight:700;color:#000;letter-spacing:-0.3px;">{vertical}</span>
          </div>
          <table style="width:100%;border-collapse:collapse;">
            {rows}
          </table>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','Helvetica Neue',sans-serif;">

  <div style="max-width:720px;margin:0 auto;padding:48px 24px 64px;">

    <!-- Header -->
    <div style="margin-bottom:40px;padding-bottom:32px;border-bottom:1px solid #e8e8e8;">
      <div style="font-size:13px;font-weight:600;color:#1a73e8;letter-spacing:0.5px;text-transform:uppercase;margin-bottom:12px;">CapitalG Scout</div>
      <h1 style="margin:0 0 8px;font-size:34px;font-weight:700;color:#000;letter-spacing:-1px;line-height:1.1;">This week's targets.</h1>
      <p style="margin:0;font-size:16px;color:#888;line-height:1.5;">
        {len(people)} executive prospects surfaced through podcast<br>appearances, industry honors, and conference activity.
      </p>
      <p style="margin:16px 0 0;font-size:13px;color:#bbb;">{today}</p>
    </div>

    <!-- Stats -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:48px;">
      <tr>{stats_html}</tr>
    </table>

    <!-- Vertical Sections -->
    {sections_html}

    <!-- Footer -->
    <div style="margin-top:48px;padding-top:24px;border-top:1px solid #e8e8e8;">
      <p style="margin:0;font-size:12px;color:#bbb;">Sent automatically every Sunday · CapitalG Scout</p>
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
