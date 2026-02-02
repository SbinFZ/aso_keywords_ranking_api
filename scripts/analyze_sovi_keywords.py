import asyncio
import json
import os
import httpx
from datetime import datetime
from app.mzsearchhints import fetch_keyword_popularity
from app.itunes_search import fetch_search_rank

# Target App ID for Sovi AI
TARGET_APP_ID = "6740720452"

# Distilled keywords based on App Store content
KEYWORDS = [
    "sovi",
    "sovi.ai", 
    "sovi ai",
    "math tutor",
    "ai math",
    "math solver",
    "scan math", 
    "homework helper",
    "study buddy",
    "calculus",
    "algebra",
    "sat prep",
    "act math",
    "ap calculus",
    "education ai"
]

async def analyze_keywords():
    results = []
    print(f"Starting enriched analysis for {len(KEYWORDS)} keywords...")
    print(f"Target App ID: {TARGET_APP_ID}")
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        for kw in KEYWORDS:
            print(f"Querying: {kw}")
            try:
                # 1. Get Popularity
                pop_data = await fetch_keyword_popularity(client, kw, country="US")
                
                # 2. Get Search Rank & Results
                # Add delay to avoid rate limits
                await asyncio.sleep(0.5)
                search_data = await fetch_search_rank(client, kw, TARGET_APP_ID, country="US")
                
                # Merge data
                merged = {**pop_data, **search_data}
                results.append(merged)
                
            except Exception as e:
                print(f"Error for {kw}: {e}")
                results.append({
                    "keyword": kw,
                    "error": str(e)
                })

    # Sort by Rank (if ranked), then by Priority
    # We want visible ranks (1, 2, 3...) first, then unranked by priority
    def sort_key(x):
        rank = x.get("rank")
        prio = x.get("priority", 0)
        # If ranked, sort by rank asc (lower is better)
        # If unranked, sort by priority desc (higher is better)
        # We can simulate this by tuple: (is_unranked, rank, -priority)
        is_unranked = 1 if rank is None else 0
        safe_rank = rank if rank is not None else 0
        return (is_unranked, safe_rank, -prio)

    results.sort(key=sort_key)

    # Generate filename with timestamp
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f"sovi_ai_keywords_enriched_{ts}.json"
    md_filename = f"sovi_ai_keywords_enriched_{ts}.md"

    # Save JSON
    with open(json_filename, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved JSON report to {json_filename}")

    # Save Markdown
    with open(md_filename, "w") as f:
        f.write(f"# Sovi.AI Enriched Keyword Analysis\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**App:** Sovi.AI - AI Math Tutor (ID: {TARGET_APP_ID})\n\n")
        
        f.write("| Keyword | Rank | Results | Priority | Score | Top App | Source |\n")
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
    
    # Print summary
    print("\nAnalysis Complete. Top Ranked Keywords:")
    for r in results:
        if r.get("rank"):
            print(f"#{r['rank']}: {r['keyword']} (Vol: {r['priority']})")

if __name__ == "__main__":
    asyncio.run(analyze_keywords())
