# Homebox Vision Importer 📷🧠

A lightweight, mobile-friendly companion application (often deployed as a "plugin-style" utility in homelabs) that lets you snap a photo of a shelf, box, or workbench of items, run it through Gemini or Claude Vision to automatically extract individual items, and bulk-import them to your Homebox instance with a single click.

No more typing out details for every single bottle of car cleaner, screw box, or tool in your workshop!

---

## Features

- **📱 Mobile Camera Friendly**: Responsive web UI designed for phones. Clicking the camera button directly opens your device's native camera.
- **🔄 Auto API Version Detection**: Compatible with both modern Homebox (v0.26.0+ with "Entity Merge" `/api/v1/entities`) and older Homebox instances (`/api/v1/items` & `/api/v1/locations`).
- **🤖 Gemini & Claude Support**: Supports Google Gemini 1.5 Flash (utilizing native Structured JSON Outputs) and Anthropic Claude 3.5 Sonnet/Haiku.
- **🛠️ Review Before Importing**: Displays identified items in an interactive spreadsheet-like grid, allowing you to edit names, quantities, and descriptions, delete false positives, or add missing rows before importing.
- **📂 Location & Type Selection**: Dynamically fetches your existing Homebox locations. If you're running a modern Homebox instance, it also fetches non-location "Entity Types" (e.g. Asset, Tool, Consumable) to properly tag items during creation.

---

## Getting Started

### 1. Retrieve Configurations

#### Homebox Configurations:
1. Log into your **Homebox** instance.
2. Go to your **Profile / User Settings**.
3. Under **API Keys**, generate a new personal API token (these start with `hb_`).
4. Note your Homebox URL (e.g., `http://192.168.1.100:7745`).

#### AI Vision Configurations (Get at least one):
- **Google Gemini API Key:** Get a free/pay-as-you-go key from [Google AI Studio](https://aistudio.google.com/).
- **Anthropic Claude API Key:** Get an API key from the [Anthropic Console](https://console.anthropic.com/).

---

### 2. Deployment

#### Option A: Docker Compose (Recommended)

Copy the `docker-compose.yml` into your homelab stacks folder and update the values:

```yaml
version: "3.8"

services:
  homebox-vision-importer:
    image: homebox-vision-importer:latest
    build: https://github.com/bmcgee/homebox-vision-importer.git # Or build from local directory
    container_name: homebox-vision-importer
    ports:
      - "8082:8000"
    restart: unless-stopped
    environment:
      - HOMEBOX_URL=http://your-homebox-ip:7745
      - HOMEBOX_API_KEY=hb_your_generated_token
      - GEMINI_API_KEY=your_gemini_api_key  # Optional
      - ANTHROPIC_API_KEY=your_anthropic_api_key  # Optional
      - LLM_PROVIDER=gemini # 'gemini' or 'claude'
```

Run command:
```bash
docker compose up -d --build
```

Access the app on `http://<your-server-ip>:8082`.

---

#### Option B: Python (Local Run)

1. Clone or navigate to the directory.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your keys:
   ```bash
   cp .env.example .env
   ```
4. Start the application:
   ```bash
   python app.py
   ```
5. Open your browser and navigate to `http://localhost:8000`.

---

## How to Use

1. **Set target location:** Open the companion app, select the target location from the dropdown, and select an Item Type (if using a newer Homebox version).
2. **Photograph items:** Click "Take Photo" to use your mobile camera or click "Browse Files" to upload an image.
3. **Analyze:** Click the "Analyze & Identify Items" button.
4. **Refine:** The AI will return a list of identified items. In the review table, you can:
   - Double-check and rename items.
   - Adjust quantities or update visual descriptions.
   - Deselect the checkbox next to any item you don't want to import.
   - Add new rows manually if the AI missed anything.
5. **Import:** Click the green **"Import Approved Items"** button. The app will import all checked items into the selected location automatically!

---

## Configurable Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `HOMEBOX_URL` | The base URL of your Homebox instance. | `http://localhost:7745` |
| `HOMEBOX_API_KEY` | Your personal Homebox API token (prefixed with `hb_`). | None (Required) |
| `GEMINI_API_KEY` | Google Gemini API key. | None |
| `ANTHROPIC_API_KEY` | Anthropic API key. | None |
| `LLM_PROVIDER` | Default LLM provider to use (`gemini` or `claude`). | `gemini` |
| `GEMINI_MODEL` | Gemini vision model. | `gemini-1.5-flash` |
| `CLAUDE_MODEL` | Claude vision model. | `claude-3-5-sonnet-20240620` |
