import os
import json
import logging
from typing import List, Optional
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env file if it exists (for local development fallback)
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

# Persistent storage folder setup (/data by default, fallback to local directory)
DATA_DIR = "/data"
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create /data directory: {e}. Falling back to local directory.")
        DATA_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
logger.info(f"Using settings directory: {DATA_DIR} (config path: {CONFIG_PATH})")

# In-memory config dictionary
config = {
    "homebox_url": "",
    "homebox_api_key": "",
    "gemini_api_key": "",
    "anthropic_api_key": "",
    "llm_provider": "gemini",
    "gemini_model": "gemini-1.5-flash",
    "claude_model": "claude-3-5-sonnet-20240620"
}

def save_config_to_file():
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        logger.info("Configuration saved to file.")
    except Exception as e:
        logger.error(f"Error saving config file: {e}")

def load_config_from_file():
    global config
    # 1. Start by loading from env variables as default bootstrap
    env_config = {
        "homebox_url": os.getenv("HOMEBOX_URL", "").rstrip("/"),
        "homebox_api_key": os.getenv("HOMEBOX_API_KEY", ""),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "llm_provider": os.getenv("LLM_PROVIDER", "gemini").lower(),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
        "claude_model": os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20240620")
    }

    # 2. Check if persistent file exists
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                loaded = json.load(f)
                # Update our in-memory config with file contents
                for k, v in loaded.items():
                    if k in config:
                        config[k] = v
            logger.info("Loaded configuration from config.json")
        except Exception as e:
            logger.error(f"Error reading config.json: {e}, falling back to env variables.")
            config.update(env_config)
    else:
        # No file yet, bootstrap with environment variables
        config.update(env_config)
        save_config_to_file()
        logger.info("Bootstrapped configuration from environment variables.")

# Load configuration on start
load_config_from_file()

# Helper: Parse Base64 Image
def clean_base64(base64_str: str):
    if "," in base64_str:
        return base64_str.split(",")[1]
    return base64_str

# Helper: Homebox Headers
def get_homebox_headers():
    token = config["homebox_api_key"]
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
        for key in possible_keys:
            if key in data and isinstance(data[key], list):
                return data[key]
        for k, v in data.items():
            if isinstance(v, list):
                return v
    return []

# Helper: Auto-detect Homebox API Version
def detect_homebox_version() -> str:
    url = f"{config['homebox_url']}/api/v1/entity-types"
    headers = get_homebox_headers()
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            return "modern"
    except Exception as e:
        logger.warning(f"Error checking version, falling back to legacy: {e}")
    return "legacy"

# Request/Response Models
class SettingsUpdate(BaseModel):
    homebox_url: str
    homebox_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_provider: str
    gemini_model: Optional[str] = "gemini-1.5-flash"
    claude_model: Optional[str] = "claude-3-5-sonnet-20240620"

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

# Web Dashboard Serving
@app.get("/", response_class=HTMLResponse)
async def get_index():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(template_path):
        with open(template_path, "r") as f:
            return f.read()
    else:
        return "<html><body><h1>Homebox Vision Importer</h1><p>templates/index.html is missing.</p></body></html>"

# Get Config and Settings Endpoint (Masking Sensitive Keys)
@app.get("/api/config")
async def get_config():
    return {
        "homebox_configured": bool(config["homebox_url"] and config["homebox_api_key"]),
        "homebox_url": config["homebox_url"],
        "gemini_configured": bool(config["gemini_api_key"]),
        "claude_configured": bool(config["anthropic_api_key"]),
        "llm_provider": config["llm_provider"],
        "gemini_model": config["gemini_model"],
        "claude_model": config["claude_model"],
        # Mask keys for security
        "has_homebox_api_key": bool(config["homebox_api_key"]),
        "has_gemini_api_key": bool(config["gemini_api_key"]),
        "has_anthropic_api_key": bool(config["anthropic_api_key"])
    }

# Save Settings Endpoint
@app.post("/api/settings")
async def update_settings(settings: SettingsUpdate):
    global config
    
    config["homebox_url"] = settings.homebox_url.rstrip("/")
    config["llm_provider"] = settings.llm_provider.lower()
    
    if settings.gemini_model:
        config["gemini_model"] = settings.gemini_model
    if settings.claude_model:
        config["claude_model"] = settings.claude_model
        
    # Check if they updated keys. Preserve old key if the input is empty or masked (********)
    if settings.homebox_api_key and settings.homebox_api_key != "********":
        config["homebox_api_key"] = settings.homebox_api_key
        
    if settings.gemini_api_key and settings.gemini_api_key != "********":
        config["gemini_api_key"] = settings.gemini_api_key
    elif settings.gemini_api_key == "":
        config["gemini_api_key"] = ""  # Clear key if explicitly emptied
        
    if settings.anthropic_api_key and settings.anthropic_api_key != "********":
        config["anthropic_api_key"] = settings.anthropic_api_key
    elif settings.anthropic_api_key == "":
        config["anthropic_api_key"] = ""  # Clear key if explicitly emptied

    save_config_to_file()
    
    return {"status": "success", "message": "Settings updated successfully."}

# Locations & Item Types Fetching
@app.get("/api/locations")
async def get_locations():
    if not (config["homebox_url"] and config["homebox_api_key"]):
        raise HTTPException(status_code=400, detail="Homebox credentials are not configured.")
        
    version = detect_homebox_version()
    headers = get_homebox_headers()
    
    locations = []
    item_types = []
    
    if version == "modern":
        # Fetch modern entity types
        try:
            r_types = requests.get(f"{config['homebox_url']}/api/v1/entity-types", headers=headers, timeout=10)
            r_types.raise_for_status()
            raw_types = extract_list_from_response(r_types.json(), ["entityTypes", "data"])
            
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

        # Fetch entities and filter locations
        try:
            r_entities = requests.get(f"{config['homebox_url']}/api/v1/entities?isLocation=true", headers=headers, timeout=10)
            r_entities.raise_for_status()
            raw_entities = extract_list_from_response(r_entities.json(), ["entities", "data"])
            
            for ent in raw_entities:
                ent_type = ent.get("entityType", {}) or {}
                is_loc = ent.get("isLocation")
                if is_loc is None:
                    is_loc = ent_type.get("isLocation", False)
                ent_type_id = ent.get("entityTypeId")
                
                if is_loc or (ent_type_id in location_type_ids):
                    locations.append({
                        "id": ent.get("id"),
                        "name": ent.get("name")
                    })
            
            # Fallback if filtering failed
            if not locations:
                r_all = requests.get(f"{config['homebox_url']}/api/v1/entities", headers=headers, timeout=10)
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
            r = requests.get(f"{config['homebox_url']}/api/v1/locations", headers=headers, timeout=10)
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
    provider = req.provider or config["llm_provider"]
    image_data = clean_base64(req.image_base64)
    mime_type = "image/jpeg"
    
    system_prompt = (
        "You are an expert inventory cataloging assistant. You are given a photo of one or more items "
        "(for example, tools, bottles, parts, or goods on a shelf or workbench). Your task is to identify "
        "each individual distinct item in the photo.\n"
        "For each item, identify:\n"
        "1. name: A concise, clear, and specific item name (e.g., 'WD-40 Multi-Use Product', 'DeWalt 20V Max Drill', 'Blue Microfiber Cloth').\n"
        "2. description: A brief description containing visual details, brand names, color, volume/weight if visible, and state (e.g., '12oz spray bottle, half full', 'Yellow/black cordless drill, missing battery').\n"
        "3. quantity: The quantity of the item (usually 1.0, but could be more if multiple identical items are grouped together).\n\n"
        "Return the results as a JSON object with a single key 'items' containing a list of these items. "
        "Each list element must contain 'name', 'description', and 'quantity' (as a number).\n"
        "Do not write any text outside of the JSON block."
    )

    if provider == "gemini":
        if not config["gemini_api_key"]:
            raise HTTPException(status_code=400, detail="Gemini API Key is not configured.")
            
        gemini_model = config["gemini_model"]
        logger.info(f"Calling Gemini ({gemini_model})")
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={config['gemini_api_key']}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_prompt},
                        {"inlineData": {"mimeType": mime_type, "data": image_data}}
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
                raise HTTPException(status_code=500, detail=f"Gemini API Error: {r.text}")
            resp_json = r.json()
            raw_text = resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            return json.loads(raw_text)
        except Exception as e:
            logger.error(f"Gemini call error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    elif provider == "claude":
        if not config["anthropic_api_key"]:
            raise HTTPException(status_code=400, detail="Claude API Key is not configured.")
            
        claude_model = config["claude_model"]
        logger.info(f"Calling Claude ({claude_model})")
        claude_url = "https://api.anthropic.com/v1/messages"
        
        headers = {
            "x-api-key": config["anthropic_api_key"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": claude_model,
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime_type, "data": image_data}
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
                raise HTTPException(status_code=500, detail=f"Claude API Error: {r.text}")
            resp_json = r.json()
            raw_text = resp_json["content"][0]["text"].strip()
            
            # Strip markdown formatting block
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            
            return json.loads(raw_text.strip())
        except Exception as e:
            logger.error(f"Claude call error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

# Bulk Import Endpoint
@app.post("/api/import")
async def import_items(req: ImportRequest):
    if not (config["homebox_url"] and config["homebox_api_key"]):
        raise HTTPException(status_code=400, detail="Homebox credentials are not configured.")
        
    version = detect_homebox_version()
    headers = get_homebox_headers()
    imported_count = 0
    errors = []
    
    for item in req.items:
        try:
            if version == "modern":
                payload = {
                    "name": item.name,
                    "description": item.description,
                    "parentId": req.location_id,
                    "quantity": float(item.quantity)
                }
                if req.item_type_id:
                    payload["entityTypeId"] = req.item_type_id
                post_url = f"{config['homebox_url']}/api/v1/entities"
            else:
                payload = {
                    "name": item.name,
                    "description": item.description,
                    "locationId": req.location_id,
                    "quantity": int(item.quantity)
                }
                post_url = f"{config['homebox_url']}/api/v1/items"

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
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
