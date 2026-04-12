#!/usr/bin/env python3
"""
Generate a daily finance blog post using OpenAI and prepend it to index.html.

Expected environment variables:
  OPENAI_API_KEY  — OpenAI secret key

Reads  : topics-used.json  (list of already-published titles/slugs)
Writes : posts/<slug>.html
         index.html         (new card prepended to .blog-grid)
         topics-used.json   (updated)
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from openai import OpenAI

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"
INDEX_HTML = REPO_ROOT / "index.html"
TOPICS_FILE = REPO_ROOT / "topics-used.json"

# ---------------------------------------------------------------------------
# Topic pool — the script picks from these categories
# ---------------------------------------------------------------------------
TOPIC_POOL = [
    "personal finance fundamentals",
    "equity investing strategies",
    "quantitative finance concepts",
    "quantitative trading strategies",
    "portfolio construction and management",
    "financial statement analysis",
    "financial analysis tools and software",
    "macroeconomics and its market impact",
    "fixed income and bond investing",
    "options, derivatives, and hedging",
    "risk management frameworks",
    "behavioral finance and investor psychology",
    "factor investing and smart beta",
    "technical analysis methods",
    "fundamental analysis deep-dives",
    "alternative investments (private equity, real assets, hedge funds)",
    "ESG and sustainable investing",
    "financial modeling techniques",
    "current news and trends in finance (early 2026)",
    "cryptocurrency, digital assets, and DeFi",
    "retirement planning and tax-advantaged accounts",
    "real estate investing and REITs",
    "algorithmic and systematic trading",
    "machine learning applications in finance",
    "central bank policy and interest rate dynamics",
    "global currency markets and FX trading",
    "sector rotation and thematic investing",
    "credit analysis and high-yield bonds",
    "volatility investing and VIX strategies",
    "wealth management and financial planning frameworks",
]


# ---------------------------------------------------------------------------
# Topic persistence
# ---------------------------------------------------------------------------

def load_used_topics() -> dict:
    if TOPICS_FILE.exists():
        return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    return {"topics": [], "slugs": []}


def save_used_topics(data: dict) -> None:
    TOPICS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Existing post titles (for de-duplication prompt context)
# ---------------------------------------------------------------------------

def get_existing_titles() -> list[str]:
    titles = []
    for post_file in POSTS_DIR.glob("*.html"):
        content = post_file.read_text(encoding="utf-8")
        m = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.DOTALL)
        if m:
            titles.append(re.sub(r"<[^>]+>", "", m.group(1)).strip())
    return titles


# ---------------------------------------------------------------------------
# OpenAI generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a finance and investing writer for a personal blog.
Write high-quality, accurate, engaging posts aimed at educated non-specialists.
Posts are 6-10 minute reads (≈1,400–2,200 words of body prose).

Formatting rules:
- Use <h2> for section headings, <h3> for sub-headings.
- Use <p>, <ul>, <ol>, <li>, <strong>, <em>, <blockquote>, <pre><code>...</code></pre>.
- Add HTML tables (<table><thead><tbody><tr><th><td>) when they clarify comparisons.
- Add Mermaid diagrams inside <pre class="mermaid">...</pre> when a flowchart or
  process diagram genuinely aids understanding (flowchart TD syntax).
- End the article with <hr /> followed by
  <p>Questions or thoughts? Find me at <a href="https://shrutinarmeti.github.io">shrutinarmeti.github.io</a>.</p>

Output ONLY a single valid JSON object — no markdown fences — with these keys:
  title        : full post title (string)
  slug         : URL-safe filename without .html, e.g. "understanding-bond-duration" (string)
  description  : 1-2 sentence excerpt for meta tag and index card (string)
  tags         : array of 2-4 tag strings, e.g. ["Investing", "Fixed Income"]
  read_time    : e.g. "8 min read" (string)
  article_html : inner content of <article class="prose">…</article>,
                 starting with <p> and ending with the contact paragraph.
                 Do NOT include the outer <article> tags.
"""


def generate_post(client: OpenAI, used_data: dict) -> tuple[dict, str]:
    """Call OpenAI and return (parsed JSON data, date_iso string)."""
    est = timezone(timedelta(hours=-5))
    today_dt = datetime.now(est)
    today_iso = today_dt.strftime("%Y-%m-%d")
    today_str = f"{today_dt.strftime('%B')} {today_dt.day}, {today_dt.year}"

    existing_titles = get_existing_titles()
    used_topics_list = used_data.get("topics", [])

    existing_info = (
        "\n".join(f"  - {t}" for t in existing_titles) if existing_titles else "  (none yet)"
    )
    used_info = (
        "\n".join(f"  - {t}" for t in used_topics_list) if used_topics_list else "  (none yet)"
    )
    pool_info = "\n".join(f"  - {t}" for t in TOPIC_POOL)

    user_prompt = f"""\
Today is {today_str}.

Posts already published (do NOT repeat or closely overlap these):
{existing_info}

Topic areas already covered (avoid similar angles):
{used_info}

Topic category pool (choose one fresh, specific angle NOT yet covered):
{pool_info}

Pick an interesting, specific topic and write the full blog post for today ({today_str}).
Add tables or Mermaid diagrams only where they genuinely add clarity.
Return ONLY the JSON object described in the system prompt.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=4096,
    )

    raw = response.choices[0].message.content.strip()
    # Strip accidental markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    return data, today_iso


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

def build_post_html(data: dict, date_iso: str) -> str:
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    date_str = f"{dt.strftime('%B')} {dt.day}, {dt.year}"

    tags_html = "\n".join(
        f'            <span class="tag">{tag}</span>' for tag in data["tags"]
    )

    # Escape braces in article_html so f-string doesn't choke
    article_html = data["article_html"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{data["title"]} — Shruti Narmeti</title>
  <meta name="description" content="{data["description"]}" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="../styles.css" />
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{ startOnLoad: true, theme: 'dark' }});</script>
</head>
<body>

  <!-- ===== HEADER ===== -->
  <header class="site-header">
    <div class="container">
      <a href="https://shrutinarmeti.github.io" class="back-btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Portfolio
      </a>
      <span class="site-title">Shruti<span>.</span>Blogs</span>
    </div>
  </header>

  <main>
    <!-- ===== POST HEADER ===== -->
    <div class="post-header">
      <div class="container">
        <div class="post-meta">
          <time datetime="{date_iso}">{date_str}</time>
          <span>·</span>
          <span>{data["read_time"]}</span>
          <div class="tags">
{tags_html}
          </div>
        </div>
        <h1>{data["title"]}</h1>
        <p class="description">{data["description"]}</p>
      </div>
    </div>

    <!-- ===== POST CONTENT ===== -->
    <section class="post-content">
      <div class="container">
        <article class="prose">

{article_html}

        </article>
      </div>
    </section>
  </main>

  <!-- ===== POST NAV ===== -->
  <div class="post-nav">
    <div class="container">
      <a href="../index.html">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        All posts
      </a>
    </div>
  </div>

  <!-- ===== FOOTER ===== -->
  <footer class="site-footer">
    <div class="container">
      <p>© 2025 <a href="https://shrutinarmeti.github.io">Shruti Narmeti</a>. All rights reserved.</p>
    </div>
  </footer>

</body>
</html>
"""


def build_card_html(data: dict, date_iso: str, slug: str) -> str:
    dt = datetime.strptime(date_iso, "%Y-%m-%d")
    date_str = f"{dt.strftime('%B')} {dt.day}, {dt.year}"

    tags_html = "\n".join(
        f'            <span class="tag">{tag}</span>' for tag in data["tags"]
    )

    cal_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
        '<line x1="16" y1="2" x2="16" y2="6"/>'
        '<line x1="8" y1="2" x2="8" y2="6"/>'
        '<line x1="3" y1="10" x2="21" y2="10"/></svg>'
    )
    arrow_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="9 18 15 12 9 6"/></svg>'
    )

    return f"""
        <!-- {date_iso} -->
        <article class="blog-card">
          <div class="blog-card-meta">
            <time datetime="{date_iso}">
              {cal_svg}
              {date_str}
            </time>
            <span>·</span>
            <span>{data["read_time"]}</span>
          </div>
          <h2><a href="posts/{slug}.html">{data["title"]}</a></h2>
          <p>{data["description"]}</p>
          <div class="tags">
{tags_html}
          </div>
          <a href="posts/{slug}.html" class="read-more">
            Read more
            {arrow_svg}
          </a>
        </article>"""


# ---------------------------------------------------------------------------
# index.html patching
# ---------------------------------------------------------------------------

def prepend_card_to_index(card_html: str) -> None:
    content = INDEX_HTML.read_text(encoding="utf-8")
    marker = '<div class="blog-grid">'
    idx = content.find(marker)
    if idx == -1:
        raise ValueError('Could not find <div class="blog-grid"> in index.html')
    insert_at = idx + len(marker)
    content = content[:insert_at] + card_html + "\n" + content[insert_at:]
    INDEX_HTML.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Slug uniqueness guard
# ---------------------------------------------------------------------------

def safe_slug(base_slug: str, used_slugs: list[str], date_iso: str) -> str:
    slug = base_slug
    if slug in used_slugs or (POSTS_DIR / f"{slug}.html").exists():
        slug = f"{base_slug}-{date_iso}"
    return slug


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    used_data = load_used_topics()

    print("Calling OpenAI to generate post…")
    data, date_iso = generate_post(client, used_data)

    slug = safe_slug(data["slug"], used_data.get("slugs", []), date_iso)
    data["slug"] = slug

    print(f"  Title : {data['title']}")
    print(f"  Slug  : {slug}")
    print(f"  Date  : {date_iso}")
    print(f"  Tags  : {data['tags']}")
    print(f"  Read  : {data['read_time']}")

    # Write post HTML
    post_path = POSTS_DIR / f"{slug}.html"
    post_path.write_text(build_post_html(data, date_iso), encoding="utf-8")
    print(f"Wrote {post_path.relative_to(REPO_ROOT)}")

    # Prepend card to index.html
    card_html = build_card_html(data, date_iso, slug)
    prepend_card_to_index(card_html)
    print("Updated index.html")

    # Persist used topics
    used_data.setdefault("topics", []).append(data["title"])
    used_data.setdefault("slugs", []).append(slug)
    save_used_topics(used_data)
    print("Updated topics-used.json")


if __name__ == "__main__":
    main()
