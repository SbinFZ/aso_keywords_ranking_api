import httpx
from typing import Optional, Dict, Any

async def fetch_search_rank(
    client: httpx.AsyncClient,
    keyword: str,
    target_app_id: str,
    country: str = "US"
) -> Dict[str, Any]:
    """
    Search iTunes API for a keyword and find the rank of target_app_id.
    Returns: {
        "total_results": int,
        "rank": int | None,  # None if not found in top N
        "top_app": str | None # Name of the #1 app
    }
    """
    url = "https://itunes.apple.com/search"
    params = {
        "term": keyword,
        "country": country,
        "entity": "software",
        "limit": 200  # Check top 200
    }
    
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        result_count = data.get("resultCount", 0)
        results = data.get("results", [])
        
        rank = None
        for i, item in enumerate(results):
            # trackId is int in API, input is str usually
            if str(item.get("trackId")) == str(target_app_id):
                rank = i + 1
                break
        
        top_app = results[0].get("trackName") if results else None
        
        return {
            "total_results": result_count,
            "rank": rank,
            "top_app": top_app
        }
        
    except Exception as e:
        print(f"Search error for {keyword}: {e}")
        return {
            "total_results": -1,
            "rank": None,
            "top_app": None,
            "error": str(e)
        }
