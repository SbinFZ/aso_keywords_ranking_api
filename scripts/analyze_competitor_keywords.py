import asyncio
import json
import os
import httpx
from datetime import datetime
from app.mzsearchhints import fetch_keyword_popularity
from app.itunes_search import fetch_search_rank

# Target App ID for Sovi AI (to check rank against competitor keywords)
TARGET_APP_ID = "6740720452"

# Distilled keywords based on Competitor Analysis (Question.AI, Solvely.AI, Gauthmath, Photomath, Answer.AI)
KEYWORDS = [
    # Core Functionality
    "ai homework helper",
    "math homework helper",
    "scan to solve",
    "photo math",
    "math scanner",
    "step by step math",
    "snap math",
    "picture math",
    "math camera",
    "solve math problems",
    
    # Specific Subjects
    "geometry solver",
    "algebra solver",
    "calculus solver",
    "trigonometry solver",
    "statistics solver",
    "chemistry helper",
    "physics helper",
    "biology helper",
    "science answer",
    
    # AI/Chatbot Specific
    "ai tutor",
    "chat with ai",
    "ai study companion",
    "ask ai",
    "question ai",
    "answer ai",
    
    # User Intent/Pain Points
    "homework answers",
    "study helper",
    "test prep",
    "exam helper",
    "math explanations",
    "free math solver",
    "math app",
    "word problem solver",
    "math word problems"
]

async def analyze_keywords():
    results = []
    print(f"Starting enriched analysis for {len(KEYWORDS)} keywords...")
    print(f"Target App: Sovi AI (ID: {TARGET_APP_ID})")
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        for kw in KEYWORDS:
            print(f"Querying: {kw}")
            try:
                # 1. Get Popularity
                pop_data = await fetch_keyword_popularity(client, kw, country="US")
                
                # 2. Get Search Rank & Results
                await asyncio.sleep(0.5) # Polite delay
                search_data = await fetch_search_rank(client, kw, TARGET_APP_ID, country="US")
                
                # Merge
                merged = {**pop_data, **search_data}
                results.append(merged)
                
            except Exception as e:
                print(f"Error for {kw}: {e}")
                results.append({
                    "keyword": kw,
                    "error": str(e)
                })

    # Sort logic: 
    # 1. Ranked keywords (ascending rank)
    # 2. Unranked keywords (descending priority)
    def sort_key(x):
        rank = x.get("rank")
        prio = x.get("priority", 0)
        is_unranked = 1 if rank is None else 0
        safe_rank = rank if rank is not None else 0
        return (is_unranked, safe_rank, -prio)

    results.sort(key=sort_key)

    # Generate filename with timestamp
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f"competitor_keywords_enriched_{ts}.json"
    md_filename = f"competitor_keywords_enriched_{ts}.md"

    # Save JSON
    with open(json_filename, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved JSON report to {json_filename}")

    # Save Markdown
    with open(md_filename, "w") as f:
        f.write(f"# Competitor Keywords Enriched Analysis\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Target App:** Sovi.AI (ID: {TARGET_APP_ID})\n")
        f.write(f"**Scope:** High-value keywords from competitors (Question.AI, Photomath, etc.)\n\n")
        
        f.write("| Keyword | Rank (Sovi) | Results | Priority | Score | Top App | Source |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        
        for r in results:
            if "error" in r:
                f.write(f"| {r['keyword']} | Error | - | - | - | - | {r['error']} |\n")
            else:
                rank = f"**#{r['rank']}**" if r.get('rank') else "-"
                total = r.get("total_results", 0)
                p = r.get("priority", 0)
                s = r.get("normalized_score", 0)
                top = r.get("top_app", "-")
                src = r.get("source", "unknown")
                f.write(f"| {r['keyword']} | {rank} | {total} | {p} | {s:.2f} | {top} | {src} |\n")
    
    print(f"Saved Markdown report to {md_filename}")
    
    # Print Top Opportunities (High Priority, No Rank)
    print("\nTop Opportunities (High Priority, Unranked):")
    unranked = [r for r in results if not r.get('rank')]
    # unranked is already sorted by priority desc due to main sort key logic
    for r in unranked[:5]:
         print(f"{r['keyword']}: Priority {r.get('priority')} (Top: {r.get('top_app')})")

    # Print Current Ranks
    print("\nCurrent Rankings:")
    ranked = [r for r in results if r.get('rank')]
    for r in ranked:
        print(f"#{r['rank']}: {r['keyword']}")

if __name__ == "__main__":
    asyncio.run(analyze_keywords())
