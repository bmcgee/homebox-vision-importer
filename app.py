import os
import json
import base64
import logging
from typing import List, Optional
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env file if it exists
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("homebox-vision")

app = FastAPI(title="Homebox Vision Importer")

# CORS middleware for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration from Environment Variables
HOMEBOX_URL = os.getenv("HOMEBOX_URL", "").rstrip("/")
HOMEBOX_API_KEY = os.getenv("HOMEBOX_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20240620")

# Validation check
is_homebox_configured = bool(HOMEBOX_URL and HOMEBOX_API_KEY)

# Helper: Parse Base64 Image
def clean_base64(base64_str: str):
    if "," in base64_str:
        return base64_str.split(",")[1]
    return base64_str

# Helper: Homebox Headers
def get_homebox_headers():
    token = HOMEBOX_API_KEY
    # Handle token prefix hb_ if users don't include Bearer manually
    if not token.startswith("Bearer "):
        token = f"Bearer {token}"
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

# Helper: Parse responses robustly
def extract_list_from_response(data, possible_keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Look for typical pagination/wrapper keys
        for key in possible_keys:
            if key in data and isinstance(data[key], list):
                return data[key]
        # Or returns keys that contain lists
        for k, v in data.items():
            if isinstance(v, list):
                return v
    return []

# Helper: Auto-detect Homebox API Version
def detect_homebox_version() -> str:
    if not is_homebox_configured:
        return "unknown"
    
    url = f"{HOMEBOX_URL}/api/v1/entity-types"
    headers = get_homebox_headers()
    
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            logger.info("Detected Homebox version: modern (v0.26.0+ with Entity Merge)")
            return "modern"
        else:
            logger.info(f"Checking entity-types returned status {r.status_code}. Defaulting to legacy.")
    except Exception as e:
        logger.warning(f"Error checking version, falling back to legacy: {e}")
        
    return "legacy"

# Models
class AnalyzeRequest(BaseModel):
    image_base64: str
    provider: Optional[str] = None

class ItemImport(BaseModel):
    name: str
    quantity: float
    description: Optional[str] = ""

class ImportRequest(BaseModel):
    location_id: str
    item_type_id: Optional[str] = None
    items: List[ItemImport]

# Root Web Interface Serving
@app.get("/", response_class=HTMLResponse)
async def get_index():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(template_path):
        with open(template_path, "r") as f:
            return f.read()
    else:
        # Inline fallback HTML if template file is missing
        return """
        <html><body><h1>Homebox Vision Importer</h1>
        <p>Frontend template file not found. Please ensure <code>templates/index.html</code> is present.</p>
        </body></html>
        """

# Config Endpoint (for UI status checking)
@app.get("/api/config")
async def get_config():
    return {
        "homebox_configured": is_homebox_configured,
        "homebox_url": HOMEBOX_URL,
        "gemini_configured": bool(GEMINI_API_KEY),
        "claude_configured": bool(ANTHROPIC_API_KEY),
        "llm_provider": DEFAULT_PROVIDER
    }

# Locations & Item Types Fetching
@app.get("/api/locations")
async def get_locations():
    if not is_homebox_configured:
        raise HTTPException(status_code=400, detail="Homebox credentials are not configured on the backend.")
        
    version = detect_homebox_version()
    headers = get_homebox_headers()
    
    locations = []
    item_types = []
    
    if version == "modern":
        # In modern versions, we fetch entity types and entities.
        # 1. Fetch Entity Types
        try:
            r_types = requests.get(f"{HOMEBOX_URL}/api/v1/entity-types", headers=headers, timeout=10)
            r_types.raise_for_status()
            raw_types = extract_list_from_response(r_types.json(), ["entityTypes", "data"])
            
            # Identify types that are locations vs items
            location_type_ids = set()
            for t in raw_types:
                t_id = t.get("id")
                is_loc = t.get("isLocation", False)
                if is_loc:
                    location_type_ids.add(t_id)
                else:
                    item_types.append({
                        "id": t_id,
                        "name": t.get("name", "Asset")
                    })
        except Exception as e:
            logger.error(f"Error fetching entity types: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch entity-types: {e}")

        # 2. Fetch Entities and filter locations
        try:
            # First try the query parameter filtering
            r_entities = requests.get(f"{HOMEBOX_URL}/api/v1/entities?isLocation=true", headers=headers, timeout=10)
            r_entities.raise_for_status()
            raw_entities = extract_list_from_response(r_entities.json(), ["entities", "data"])
            
            for ent in raw_entities:
                # Add check if it actually behaves as a location
                ent_type = ent.get("entityType", {}) or {}
                # Sometimes it is flat in the object
                is_loc = ent.get("isLocation")
                if is_loc is None:
                    is_loc = ent_type.get("isLocation", False)
                
                # Also fall back to matching entityTypeId with location_type_ids
                ent_type_id = ent.get("entityTypeId")
                if is_loc or (ent_type_id in location_type_ids):
                    locations.append({
                        "id": ent.get("id"),
                        "name": ent.get("name")
                    })
                    
            # If the filter didn't work and we got nothing, query all tree nodes or try fetching all entities
            if not locations:
                r_all = requests.get(f"{HOMEBOX_URL}/api/v1/entities", headers=headers, timeout=10)
                if r_all.status_code == 200:
                    raw_all = extract_list_from_response(r_all.json(), ["entities", "data"])
                    for ent in raw_all:
                        ent_type_id = ent.get("entityTypeId")
                        ent_type = ent.get("entityType", {}) or {}
                        is_loc = ent.get("isLocation") or ent_type.get("isLocation", False) or (ent_type_id in location_type_ids)
                        if is_loc:
                            locations.append({
                                "id": ent.get("id"),
                                "name": ent.get("name")
                            })
        except Exception as e:
            logger.error(f"Error fetching entities: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch entities: {e}")
            
    else:
        # Legacy Mode (v0.25 and older)
        try:
            r = requests.get(f"{HOMEBOX_URL}/api/v1/locations", headers=headers, timeout=10)
            r.raise_for_status()
            raw_locs = extract_list_from_response(r.json(), ["locations", "data"])
            for loc in raw_locs:
                locations.append({
                    "id": loc.get("id"),
                    "name": loc.get("name")
                })
        except Exception as e:
            logger.error(f"Error fetching legacy locations: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch legacy locations: {e}")
            
    return {
        "version": version,
        "locations": locations,
        "item_types": item_types
    }

# AI Image Analysis Endpoint
@app.post("/api/analyze")
async def analyze_image(req: AnalyzeRequest):
    provider = req.provider or DEFAULT_PROVIDER
    
    if not req.image_base64:
        raise HTTPException(status_code=400, detail="Base64 image data is required.")
        
    image_data = clean_base64(req.image_base64)
    mime_type = "image/jpeg" # Default compression
    
    system_prompt = (
        "You are an expert inventory cataloging assistant. You are given a photo of one or more items "
        "(for example, tools, bottles, parts, or goods on a shelf or workbench). Your task is to identify "
        "each individual distinct item in the photo.\n"
        "For each item, identify:\n"
        "1. name: A concise, clear, and specific item name (e.g., 'WD-40 Multi-Use Product', 'DeWalt 20V Max Drill', 'Blue Microfiber Cloth').\n"
        "2. description: A brief description containing visual details, brand names, color, volume/weight if visible, and state (e.g., '12oz spray bottle, half full', 'Yellow/black cordless drill, missing battery').\n"
        "3. quantity: The quantity of the item (usually 1.0, but could be more if multiple identical items are grouped together).\n\n"
        "Return the results as a JSON object with a single key 'items' containing a list of these items. "
        "Each list element must contain 'name', 'description', and 'quantity' (as a number). "
        "Do not write any text outside of the JSON block."
    )

    if provider == "gemini":
        if not GEMINI_API_KEY:
            raise HTTPException(status_code=400, detail="Gemini API Key is not set in environment.")
            
        logger.info(f"Analyzing image with Gemini model: {GEMINI_MODEL}")
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": image_data
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "items": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "name": {"type": "STRING"},
                                    "description": {"type": "STRING"},
                                    "quantity": {"type": "NUMBER"}
                                },
                                "required": ["name", "quantity"]
                            }
                        }
                    }
                }
            }
        }
        
        try:
            r = requests.post(gemini_url, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
            if r.status_code != 200:
                logger.error(f"Gemini API returned error: {r.status_code} - {r.text}")
                raise HTTPException(status_code=500, detail=f"Gemini API Error: {r.text}")
                
            resp_json = r.json()
            # Extract content from response structure
            candidates = resp_json.get("candidates", [])
            if not candidates:
                raise HTTPException(status_code=500, detail="Gemini failed to return content candidates.")
                
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise HTTPException(status_code=500, detail="Gemini response content candidate has no parts.")
                
            raw_text = parts[0].get("text", "").strip()
            parsed_data = json.loads(raw_text)
            return parsed_data
            
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse JSON from Gemini: {je}")
            raise HTTPException(status_code=500, detail="Gemini returned malformed JSON.")
        except Exception as e:
            logger.error(f"Gemini calling error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    elif provider == "claude":
        if not ANTHROPIC_API_KEY:
            raise HTTPException(status_code=400, detail="Anthropic API Key is not set in environment.")
            
        logger.info(f"Analyzing image with Claude model: {CLAUDE_MODEL}")
        claude_url = "https://api.anthropic.com/v1/messages"
        
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": CLAUDE_MODEL,
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": f"{system_prompt}\nReturn raw JSON only, starting with {{ and ending with }}."
                        }
                    ]
                }
            ]
        }
        
        try:
            r = requests.post(claude_url, json=payload, headers=headers, timeout=60)
            if r.status_code != 200:
                logger.error(f"Claude API returned error: {r.status_code} - {r.text}")
                raise HTTPException(status_code=500, detail=f"Claude API Error: {r.text}")
                
            resp_json = r.json()
            content = resp_json.get("content", [])
            if not content:
                raise HTTPException(status_code=500, detail="Claude returned no content.")
                
            raw_text = content[0].get("text", "").strip()
            
            # Clean up markdown code block wrapping if Claude returned it
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
                
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            raw_text = raw_text.strip()
            parsed_data = json.loads(raw_text)
            return parsed_data
            
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse JSON from Claude: {je}. Raw output was: {raw_text}")
            raise HTTPException(status_code=500, detail="Claude returned malformed JSON.")
        except Exception as e:
            logger.error(f"Claude calling error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
            
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

# Bulk Import Endpoint
@app.post("/api/import")
async def import_items(req: ImportRequest):
    if not is_homebox_configured:
        raise HTTPException(status_code=400, detail="Homebox credentials are not configured on the backend.")
        
    version = detect_homebox_version()
    headers = get_homebox_headers()
    
    imported_count = 0
    errors = []
    
    logger.info(f"Starting bulk import for {len(req.items)} items in {version} mode")
    
    for item in req.items:
        try:
            if version == "modern":
                # v0.26.0+ Entity merge payload
                payload = {
                    "name": item.name,
                    "description": item.description,
                    "parentId": req.location_id,
                    "quantity": float(item.quantity)
                }
                
                # Attach entityTypeId if specified
                if req.item_type_id:
                    payload["entityTypeId"] = req.item_type_id
                else:
                    # Let the server default, or we omit if not needed
                    pass
                    
                post_url = f"{HOMEBOX_URL}/api/v1/entities"
                
            else:
                # Legacy items payload
                payload = {
                    "name": item.name,
                    "description": item.description,
                    "locationId": req.location_id,
                    "quantity": int(item.quantity)
                }
                post_url = f"{HOMEBOX_URL}/api/v1/items"

            r = requests.post(post_url, headers=headers, json=payload, timeout=10)
            if r.status_code in [200, 201]:
                imported_count += 1
            else:
                err_msg = f"Failed to import '{item.name}': HTTP {r.status_code} - {r.text}"
                logger.error(err_msg)
                errors.append(err_msg)
                
        except Exception as e:
            err_msg = f"Exception importing '{item.name}': {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    if errors and imported_count == 0:
        raise HTTPException(status_code=500, detail=f"Failed to import items. First error: {errors[0]}")
        
    return {
        "imported_count": imported_count,
        "total_count": len(req.items),
        "errors": errors
    }

if __name__ == "__main__":
    import uvicorn
    # Listen on all interfaces by default for hosting in Docker
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
