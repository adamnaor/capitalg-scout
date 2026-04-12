import anthropic
import argparse
import json
import re
from datetime import date

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

            # Extract JSON array from anywhere in the response
            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1 and end > start:
                json_str = raw[start:end + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Pull out individual complete objects if full parse fails
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


def format_report(people):
    today = date.today().strftime("%B %d, %Y")
    lines = []
    lines.append(f"CAPITALG SCOUT — {today}")
    lines.append(f"{len(people)} targets this week")
    lines.append("=" * 50)
    lines.append("")

    for i, p in enumerate(people, 1):
        lines.append(f"{i:02d}. {p.get('name', '')}")
        lines.append(f"    Role:     {p.get('title', '')} at {p.get('company', '')}")
        lines.append(f"    Vertical: {p.get('vertical', '')}")
        lines.append(f"    Google:   {p.get('google_tie', 'None found')}")
        lines.append(f"    Signal:   {p.get('signal', '')}")
        lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", "-d", type=int, default=30)
    args = parser.parse_args()
    people = run_scout(days=args.days)
    print(format_report(people))


if __name__ == "__main__":
    main()
