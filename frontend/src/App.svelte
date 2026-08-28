<script lang="ts">
  import { onMount } from 'svelte';

  // Interfaces
  interface BackendConfig {
    homebox_configured: boolean;
    homebox_url: string;
    homebox_tenant: string;
    gemini_configured: boolean;
    claude_configured: boolean;
    llm_provider: string;
    gemini_model: string;
    claude_model: string;
    homebox_api_key?: string;
    gemini_api_key?: string;
    anthropic_api_key?: string;
    has_homebox_api_key: boolean;
    has_gemini_api_key: boolean;
    has_anthropic_api_key: boolean;
  }

  interface Location {
    id: string;
    name: string;
    parent_id?: string | null;
  }

  interface NestedLocation {
    id: string;
    name: string;
    depth: number;
    parent_id?: string | null;
  }

  interface ItemType {
    id: string;
    name: string;
  }

  interface ReviewItem {
    id: string;
    checked: boolean;
    name: string;
    quantity: number;
    description: string;
  }

  // State using Svelte 5 runes
  let backendConfig = $state<BackendConfig>({
    homebox_configured: false,
    homebox_url: "",
    homebox_tenant: "",
    gemini_configured: false,
    claude_configured: false,
    llm_provider: "gemini",
    gemini_model: "gemini-3.6-flash",
    claude_model: "claude-3-5-sonnet-20240620",
    homebox_api_key: "",
    gemini_api_key: "",
    anthropic_api_key: "",
    has_homebox_api_key: false,
    has_gemini_api_key: false,
    has_anthropic_api_key: false
  });

  let statusText = $state<string>("Checking API...");
  let statusColor = $state<string>("yellow"); // 'green', 'yellow', 'red'
  
  let locations = $state<Location[]>([]);
  let itemTypes = $state<ItemType[]>([]);
  let isModernVersion = $state<boolean>(false);
  let selectedLocation = $state<string>("");
  let selectedItemType = $state<string>("");
  let selectedProvider = $state<string>("gemini");

  // Contact Sheet & Image Downsizing Settings
  let enableContactSheet = $state<boolean>(true);
  let maxImageDimension = $state<number>(800); // 600, 800, 1200
  let imageQuality = $state<number>(0.80);

  let base64Images = $state<string[]>([]);
  let isAnalyzing = $state<boolean>(false);
  let items = $state<ReviewItem[]>([]); // Items in review grid
  let selectAll = $state<boolean>(true);

  // Settings Modal state
  let settingsModalOpen = $state<boolean>(false);
  let cfgUrl = $state<string>("");
  let cfgToken = $state<string>("");
  let cfgTenant = $state<string>("");
  let cfgGeminiKey = $state<string>("");
  let cfgClaudeKey = $state<string>("");
  let cfgProvider = $state<string>("gemini");
  let cfgGeminiModel = $state<string>("gemini-3.6-flash");
  let cfgClaudeModel = $state<string>("claude-3-5-sonnet-20240620");

  // Visibility states for keys in Settings
  let showToken = $state<boolean>(false);
  let showGeminiKey = $state<boolean>(false);
  let showClaudeKey = $state<boolean>(false);

  // Analysis Live Status state
  let analysisStatus = $state<string>("Preparing image payload...");
  let analysisSubStatus = $state<string>("Encoding photos...");
  let analysisProgress = $state<number>(15);
  let activeStepIndex = $state<number>(0);

  // Error state for robust error printing
  let lastError = $state<string | null>(null);

  let fileInputRef: HTMLInputElement | undefined = undefined;
  let cameraInputRef: HTMLInputElement | undefined = undefined;
  let dropZoneOver = $state<boolean>(false);
  
  let saveSettingsBtnDisabled = $state<boolean>(false);
  let saveSettingsBtnText = $state<string>("Save Config");
  
  let attachPhotosToImport = $state<boolean>(true);
  
  let importBtnDisabled = $state<boolean>(false);
  let importBtnText = $state<string>("Import Approved Items to Homebox");

  // Derived state (computed properties)
  let selectedCount = $derived(items.filter(item => item.checked).length);
  let analyzeBtnDisabled = $derived(base64Images.length === 0 || isAnalyzing);
  let selectedLocationName = $derived(() => {
    const loc = locations.find(l => l.id === selectedLocation);
    return loc ? loc.name : "-";
  });

  onMount(() => {
    loadConfigAndCheck();
  });

  // Helper to extract detailed error messages from Response
  async function getErrorMessage(response: Response, defaultMessage: string): Promise<string> {
    try {
      const data = await response.json();
      return data.detail || defaultMessage;
    } catch {
      return `${defaultMessage} (HTTP Status: ${response.status} ${response.statusText})`;
    }
  }

  // Load Configuration and Check Status
  async function loadConfigAndCheck() {
    try {
      lastError = null;
      updateStatus('Checking config...', 'yellow');
      const response = await fetch('/api/config');
      if (!response.ok) {
        const detail = await getErrorMessage(response, 'Failed to fetch server configuration');
        throw new Error(detail);
      }
      backendConfig = await response.json();
      
      if (!backendConfig.homebox_configured) {
        updateStatus('Needs Config', 'red');
      } else {
        updateStatus('Loading locations...', 'yellow');
        await fetchLocations();
      }
      
      if (backendConfig.llm_provider) {
        selectedProvider = backendConfig.llm_provider;
      }
    } catch (error: any) {
      console.error('Initialization error:', error);
      lastError = error.message || String(error);
      updateStatus('Connection failed', 'red');
    }
  }

  function updateStatus(text: string, color: string) {
    statusText = text;
    statusColor = color;
  }

  // Fetch Locations
  async function fetchLocations() {
    try {
      lastError = null;
      const response = await fetch('/api/locations');
      if (!response.ok) {
        const detail = await getErrorMessage(response, 'Failed to fetch locations from Homebox');
        throw new Error(detail);
      }
      const data = await response.json();
      locations = data.locations || [];
      itemTypes = data.item_types || [];
      isModernVersion = data.version === "modern";
      
      // Auto-select first location if none is selected
      if (locations.length > 0 && !selectedLocation) {
        selectedLocation = locations[0].id;
      }
      
      updateStatus('Connected', 'green');
    } catch (error: any) {
      console.error(error);
      lastError = error.message || String(error);
      updateStatus('Connection failed', 'red');
    }
  }

  // Open Settings Modal & Prefill values
  function openSettings() {
    cfgUrl = backendConfig.homebox_url || '';
    cfgToken = backendConfig.homebox_api_key || '';
    cfgTenant = backendConfig.homebox_tenant || '';
    cfgProvider = backendConfig.llm_provider || 'gemini';
    cfgGeminiKey = backendConfig.gemini_api_key || '';
    cfgClaudeKey = backendConfig.anthropic_api_key || '';
    cfgGeminiModel = backendConfig.gemini_model || 'gemini-3.6-flash';
    cfgClaudeModel = backendConfig.claude_model || 'claude-3-5-sonnet-20240620';
    
    // Reset toggles
    showToken = false;
    showGeminiKey = false;
    showClaudeKey = false;
    
    settingsModalOpen = true;
  }

  function closeSettings() {
    settingsModalOpen = false;
  }

  // Save Settings to Backend
  async function saveSettings() {
    if (!cfgUrl.trim()) {
      alert("Homebox Base URL is required! Please enter a valid URL.");
      return;
    }

    saveSettingsBtnDisabled = true;
    saveSettingsBtnText = "Saving...";
    lastError = null;

    const settingsData = {
      homebox_url: cfgUrl.trim(),
      homebox_api_key: cfgToken,
      homebox_tenant: cfgTenant.trim(),
      llm_provider: cfgProvider,
      gemini_api_key: cfgGeminiKey,
      anthropic_api_key: cfgClaudeKey,
      gemini_model: cfgGeminiModel.trim(),
      claude_model: cfgClaudeModel.trim()
    };

    try {
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsData)
      });

      if (!response.ok) {
        const errDetail = await getErrorMessage(response, 'Failed to save configuration settings');
        throw new Error(errDetail);
      }

      alert('Settings saved successfully!');
      closeSettings();
      await loadConfigAndCheck();
    } catch (error: any) {
      console.error(error);
      lastError = error.message || String(error);
    } finally {
      saveSettingsBtnDisabled = false;
      saveSettingsBtnText = "Save Config";
    }
  }

  // File selection
  function triggerFileInput() {
    if (fileInputRef) fileInputRef.click();
  }

  // Camera selection
  function triggerCameraInput() {
    if (cameraInputRef) cameraInputRef.click();
  }

  async function handleFileSelect(e: Event) {
    const target = e.target as HTMLInputElement;
    if (!target.files || target.files.length === 0) return;

    const files = Array.from(target.files);
    for (const file of files) {
      await processImage(file);
    }
    target.value = '';
  }

  // Reads just the pixel dimensions of an image file.
  // We load it into an <img> but never draw it, so the browser only has to parse the
  // header — it doesn't need to decode all the pixels to tell us the size.
  function readImageSize(file: File): Promise<{ width: number; height: number }> {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const size = { width: img.naturalWidth, height: img.naturalHeight };
        URL.revokeObjectURL(url);
        if (!size.width || !size.height) reject(new Error("Image reported zero dimensions"));
        else resolve(size);
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("Browser could not read this image"));
      };
      img.src = url;
    });
  }

  // Encodes a canvas to a JPEG data URL without blocking the UI.
  // canvas.toDataURL() is synchronous — it builds the entire base64 string on the main
  // thread. toBlob() hands the encode off, and FileReader converts it async.
  function canvasToJpegDataUrl(canvas: HTMLCanvasElement, quality: number): Promise<string> {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) return reject(new Error("JPEG encoding failed"));
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      }, 'image/jpeg', quality);
    });
  }

  // Hierarchical Location Tree Helper
  function getFormattedLocations(): NestedLocation[] {
    const map = new Map<string, Location>();
    const childrenMap = new Map<string, Location[]>();
    const roots: Location[] = [];

    locations.forEach(loc => {
      map.set(loc.id, loc);
      if (loc.parent_id) {
        if (!childrenMap.has(loc.parent_id)) {
          childrenMap.set(loc.parent_id, []);
        }
        childrenMap.get(loc.parent_id)!.push(loc);
      } else {
        roots.push(loc);
      }
    });

    locations.forEach(loc => {
      if (loc.parent_id && !map.has(loc.parent_id) && !roots.includes(loc)) {
        roots.push(loc);
      }
    });

    const result: NestedLocation[] = [];

    function traverse(node: Location, depth: number) {
      result.push({
        id: node.id,
        name: node.name,
        depth: depth,
        parent_id: node.parent_id
      });

      const children = childrenMap.get(node.id) || [];
      children.sort((a, b) => a.name.localeCompare(b.name));
      children.forEach(child => traverse(child, depth + 1));
    }

    roots.sort((a, b) => a.name.localeCompare(b.name));
    roots.forEach(root => traverse(root, 0));

    return result;
  }

  // Contact Sheet Composite Grid Generator
  async function generateContactSheet(imgs: string[]): Promise<string> {
    if (imgs.length === 0) return '';
    if (imgs.length === 1) return imgs[0];

    return new Promise((resolve) => {
      const count = imgs.length;
      const cols = count <= 2 ? count : count <= 4 ? 2 : count <= 9 ? 3 : 4;
      const rows = Math.ceil(count / cols);

      const cellWidth = 600;
      const cellHeight = 450;
      const canvas = document.createElement('canvas');
      canvas.width = cols * cellWidth;
      canvas.height = rows * cellHeight;
      const ctx = canvas.getContext('2d');

      if (!ctx) {
        resolve(imgs[0]);
        return;
      }

      ctx.fillStyle = '#21222c';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      let loaded = 0;
      imgs.forEach((src, idx) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => {
          const col = idx % cols;
          const row = Math.floor(idx / cols);
          const x = col * cellWidth;
          const y = row * cellHeight;

          const scale = Math.min(cellWidth / img.width, cellHeight / img.height);
          const drawW = img.width * scale;
          const drawH = img.height * scale;
          const drawX = x + (cellWidth - drawW) / 2;
          const drawY = y + (cellHeight - drawH) / 2;

          ctx.fillStyle = '#191a21';
          ctx.fillRect(x + 4, y + 4, cellWidth - 8, cellHeight - 8);

          ctx.drawImage(img, drawX, drawY, drawW, drawH);

          // Numbered Badge overlay (Homebox Pink)
          ctx.fillStyle = 'rgba(255, 121, 198, 0.95)';
          ctx.beginPath();
          ctx.arc(x + 40, y + 40, 24, 0, 2 * Math.PI);
          ctx.fill();

          ctx.fillStyle = '#21222c';
          ctx.font = 'bold 22px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(`#${idx + 1}`, x + 40, y + 40);

          ctx.strokeStyle = '#343746';
          ctx.lineWidth = 2;
          ctx.strokeRect(x + 2, y + 2, cellWidth - 4, cellHeight - 4);

          loaded++;
          if (loaded === count) {
            canvasToJpegDataUrl(canvas, 0.85).then(resolve).catch(() => resolve(imgs[0]));
          }
        };
        img.onerror = () => {
          loaded++;
          if (loaded === count) {
            canvasToJpegDataUrl(canvas, 0.85).then(resolve).catch(() => resolve(imgs[0]));
          }
        };
        img.src = src;
      });
    });
  }

  async function processImage(file: File) {
    const fileName = file.name.toLowerCase();
    const fileType = file.type.toLowerCase();
    if (fileName.endsWith('.heic') || fileName.endsWith('.heif') || fileType.includes('heic') || fileType.includes('heif')) {
      alert(`HEIC/HEIF image "${file.name}" is not natively supported by your browser. Please convert to JPEG, PNG, or WebP first.`);
      return;
    }

    const MAX_DIM = maxImageDimension;

    try {
      const { width: srcW, height: srcH } = await readImageSize(file);

      const scale = Math.min(1, MAX_DIM / Math.max(srcW, srcH));
      const width = Math.max(1, Math.round(srcW * scale));
      const height = Math.max(1, Math.round(srcH * scale));

      const bitmap = await createImageBitmap(file, {
        resizeWidth: width,
        resizeHeight: height,
        resizeQuality: 'high'
      });

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error("Could not get a 2D canvas context");
      ctx.drawImage(bitmap, 0, 0, width, height);
      bitmap.close();

      const b64 = await canvasToJpegDataUrl(canvas, imageQuality);
      base64Images = [...base64Images, b64];
    } catch (err) {
      console.error("Failed to process image:", err);
      alert(`Could not read image "${file.name}". Try a JPEG, PNG, or WebP.`);
    }
  }

  function removeImage(index: number) {
    base64Images = base64Images.filter((_, i) => i !== index);
  }

  function resetImages() {
    base64Images = [];
    if (fileInputRef) fileInputRef.value = '';
    if (cameraInputRef) cameraInputRef.value = '';
  }

  // Drag and drop
  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    dropZoneOver = true;
  }

  function handleDragLeave() {
    dropZoneOver = false;
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    dropZoneOver = false;
    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      for (const file of files) {
        if (file.type.startsWith('image/')) {
          await processImage(file);
        }
      }
    }
  }

  // Analyze
  async function analyzePhoto() {
    if (base64Images.length === 0) return;

    items = [];
    isAnalyzing = true;
    lastError = null;

    activeStepIndex = 0;
    analysisProgress = 15;
    analysisStatus = "Preparing image payload...";
    analysisSubStatus = `Processing ${base64Images.length} photo(s)...`;

    const modelName = selectedProvider === 'gemini' 
      ? (backendConfig.gemini_model || 'gemini-3.6-flash') 
      : (backendConfig.claude_model || 'claude-3-5-sonnet');
    const providerName = selectedProvider === 'gemini' ? 'Google Gemini' : 'Anthropic Claude';

    let timerId: any = null;
    let secondsElapsed = 0;

    timerId = setInterval(() => {
      secondsElapsed += 1;

      if (secondsElapsed >= 1 && activeStepIndex < 1) {
        activeStepIndex = 1;
        analysisProgress = 35;
        analysisStatus = `Connecting to ${providerName}...`;
        analysisSubStatus = `Transmitting payload to ${modelName}`;
      } else if (secondsElapsed >= 4 && activeStepIndex < 2) {
        activeStepIndex = 2;
        analysisProgress = 65;
        analysisStatus = "Detecting items & objects...";
        analysisSubStatus = "AI vision model scanning features...";
      } else if (secondsElapsed >= 8 && activeStepIndex < 3) {
        activeStepIndex = 3;
        analysisProgress = 85;
        analysisStatus = "Cataloging descriptions & quantities...";
        analysisSubStatus = "Extracting structured attributes...";
      } else if (secondsElapsed >= 12) {
        analysisProgress = Math.min(95, 85 + Math.floor((secondsElapsed - 8) / 2));
        analysisSubStatus = `Processing request (${secondsElapsed}s elapsed)...`;
      }
    }, 1000);

    try {
      let payloadImages = base64Images;
      if (enableContactSheet && base64Images.length > 1) {
        analysisStatus = "Building Contact Sheet grid...";
        analysisSubStatus = `Combining ${base64Images.length} photos into 1 visual grid...`;
        const contactSheet = await generateContactSheet(base64Images);
        payloadImages = [contactSheet];
      }

      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          images_base64: payloadImages,
          provider: selectedProvider
        })
      });

      if (!response.ok) {
        const errDetail = await getErrorMessage(response, 'AI Vision Analysis failed');
        throw new Error(errDetail);
      }

      analysisProgress = 100;
      analysisStatus = "Parsing detected items...";

      const data = await response.json();
      items = (data.items || []).map((item: any) => ({
        id: 'item-' + Math.random().toString(36).substring(2, 9),
        checked: true,
        name: item.name || '',
        quantity: item.quantity || 1,
        description: item.description || ''
      }));
      
      selectAll = true;
    } catch (error: any) {
      console.error(error);
      lastError = error.message || String(error);
    } finally {
      if (timerId) clearInterval(timerId);
      isAnalyzing = false;
    }
  }

  // Checkbox management
  function toggleAll() {
    items = items.map(item => ({ ...item, checked: selectAll }));
  }

  function handleItemCheckboxChange() {
    selectAll = items.length > 0 && items.every(item => item.checked);
  }

  function addItem() {
    items = [...items, {
      id: 'item-' + Math.random().toString(36).substring(2, 9),
      checked: true,
      name: '',
      quantity: 1,
      description: ''
    }];
  }

  function deleteItem(id: string) {
    items = items.filter(item => item.id !== id);
  }

  // Import
  async function importApprovedItems() {
    if (!selectedLocation) {
      alert('Please select a target location!');
      return;
    }

    const approvedItems = items.filter(item => item.checked).map(item => ({
      name: item.name,
      quantity: parseFloat(item.quantity as any) || 1,
      description: item.description
    }));

    if (approvedItems.length === 0) {
      alert('Please select items to import!');
      return;
    }

    importBtnDisabled = true;
    importBtnText = "Importing...";
    lastError = null;

    try {
      const response = await fetch('/api/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          location_id: selectedLocation,
          item_type_id: selectedItemType || null,
          items: approvedItems,
          images_base64: base64Images,
          attach_photos: attachPhotosToImport
        })
      });

      const data = await response.json();
      
      if (response.ok) {
        alert(`Imported ${data.imported_count} items!`);
        items = [];
        resetImages();
      } else {
        const errDetail = await getErrorMessage(response, 'Bulk import failed');
        throw new Error(errDetail);
      }
    } catch (error: any) {
      console.error(error);
      lastError = error.message || String(error);
    } finally {
      importBtnDisabled = false;
      importBtnText = "Import Approved Items to Homebox";
    }
  }
</script>

<!-- Header -->
<header class="bg-[#21222c] border-b border-[#343746] py-3.5 px-6 shadow-md">
  <div class="max-w-6xl mx-auto flex justify-between items-center">
    <div class="flex items-center space-x-3">
      <div class="bg-[#ff79c6] p-2 rounded-lg text-[#21222c] shadow">
        <i class="fa-solid fa-cube text-xl"></i>
      </div>
      <div>
        <h1 class="text-xl font-bold tracking-tight text-[#f8f8f2] flex items-center space-x-2">
          <span>Homebox Vision</span>
          <span class="text-xs font-normal text-[#8be9fd] bg-[#343746] px-2 py-0.5 rounded-full">Importer</span>
        </h1>
        <p class="text-xs text-[#6272a4]">Homelab AI Inventory Importer</p>
      </div>
    </div>
    <div class="flex items-center space-x-3">
      <div class="flex items-center space-x-2 bg-[#1e1f29] px-3 py-1.5 rounded-full text-xs text-[#f8f8f2] border border-[#343746]">
        <span class="h-2 w-2 rounded-full animate-pulse 
          {statusColor === 'green' ? 'bg-[#50fa7b]' : (statusColor === 'red' ? 'bg-[#ff5555]' : 'bg-[#f1fa8c]')}">
        </span>
        <span>{statusText}</span>
      </div>
      <button onclick={openSettings} class="bg-[#343746] hover:bg-[#44475a] text-[#f8f8f2] border border-[#44475a] p-2 rounded-lg transition-colors cursor-pointer" title="Settings">
        <i class="fa-solid fa-gear"></i>
      </button>
    </div>
  </div>
</header>

<!-- Main Content -->
<main class="flex-grow max-w-6xl w-full mx-auto p-4 sm:p-6 pb-24 sm:pb-6 space-y-6">
  <!-- Detailed Error Alert Banner -->
  {#if lastError}
    <div class="bg-[#ff5555]/15 border border-[#ff5555]/40 rounded-xl p-4 flex items-start space-x-3 shadow-lg">
      <i class="fa-solid fa-circle-exclamation text-[#ff5555] text-xl mt-0.5"></i>
      <div class="flex-grow">
        <h3 class="text-sm font-semibold text-[#f8f8f2]">Error Occurred</h3>
        <p class="text-xs text-[#f8f8f2]/90 mt-1 font-mono break-all">{lastError}</p>
      </div>
      <button onclick={() => lastError = null} class="text-[#6272a4] hover:text-[#f8f8f2] transition-colors cursor-pointer" title="Dismiss error">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>
  {/if}

  <!-- Configuration Alert Banner -->
  {#if !backendConfig.homebox_configured}
    <div class="bg-[#f1fa8c]/10 border border-[#f1fa8c]/30 rounded-xl p-4 flex items-start space-x-3">
      <i class="fa-solid fa-triangle-exclamation text-[#f1fa8c] text-xl mt-0.5"></i>
      <div class="flex-grow">
        <h3 class="text-sm font-semibold text-[#f1fa8c]">Missing Configuration</h3>
        <p class="text-xs text-[#f8f8f2]/80 mt-1">Please configure your Homebox URL, Homebox API Key, and at least one AI API key. Click the gear icon in the header to open settings.</p>
      </div>
    </div>
  {/if}

  <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
    <!-- Left Panel: Setup and Camera (2 Cols) -->
    <div class="lg:col-span-2 space-y-6">
      <!-- Target Setup -->
      <div class="bg-[#21222c] border border-[#343746] rounded-2xl p-5 shadow-xl space-y-4">
        <h2 class="text-base font-bold text-[#8be9fd] flex items-center space-x-2">
          <i class="fa-solid fa-sliders text-[#ff79c6]"></i>
          <span>1. Setup Target</span>
        </h2>
        
        <div>
          <label for="location-select" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-2">Destination Location</label>
          <div class="flex space-x-2">
            <select id="location-select" bind:value={selectedLocation} class="flex-grow bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6] transition-colors">
              {#if locations.length === 0}
                <option value="">No locations available</option>
              {:else}
                {#each getFormattedLocations() as loc}
                  <option value={loc.id}>
                    {loc.depth > 0 ? '\u00A0\u00A0'.repeat(loc.depth) + '└─ ' : ''}{loc.name}
                  </option>
                {/each}
              {/if}
            </select>
            <button onclick={fetchLocations} class="bg-[#343746] hover:bg-[#44475a] text-[#f8f8f2] border border-[#44475a] p-2 rounded-lg transition-colors cursor-pointer" title="Reload locations">
              <i class="fa-solid fa-arrows-rotate"></i>
            </button>
          </div>
        </div>

        {#if isModernVersion}
          <div>
            <label for="item-type-select" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-2">Item Type (Entity Type)</label>
            <select id="item-type-select" bind:value={selectedItemType} class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6] transition-colors">
              <option value="">Default Asset/Item</option>
              {#each itemTypes as type}
                <option value={type.id}>{type.name}</option>
              {/each}
            </select>
          </div>
        {/if}

        <div>
          <label for="provider-select" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-2">AI Provider</label>
          <select id="provider-select" bind:value={selectedProvider} class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6] transition-colors">
            <option value="gemini">Google Gemini (Recommended)</option>
            <option value="claude">Anthropic Claude</option>
          </select>
        </div>

        <!-- Image Optimization & Contact Sheet Controls -->
        <div class="pt-3 border-t border-[#343746] space-y-3">
          <label class="flex items-center justify-between text-xs text-[#f8f8f2] font-semibold cursor-pointer">
            <span class="flex items-center space-x-1.5">
              <i class="fa-solid fa-table-cells text-[#ff79c6]"></i>
              <span>Contact Sheet Batching</span>
            </span>
            <input type="checkbox" bind:checked={enableContactSheet} class="rounded bg-[#1e1f29] border-[#343746] text-[#ff79c6] focus:ring-[#ff79c6]">
          </label>

          <div class="flex items-center justify-between text-xs">
            <span class="text-[#6272a4]">Max Dimension:</span>
            <select bind:value={maxImageDimension} class="bg-[#1e1f29] border border-[#343746] rounded px-2 py-1 text-xs text-[#f8f8f2]">
              <option value={600}>600px (Fastest)</option>
              <option value={800}>800px (Balanced)</option>
              <option value={1200}>1200px (Full Detail)</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Camera / Upload -->
      <div class="bg-[#21222c] border border-[#343746] rounded-2xl p-5 shadow-xl space-y-4">
        <h2 class="text-base font-bold text-[#8be9fd] flex items-center space-x-2">
          <i class="fa-solid fa-camera text-[#ff79c6]"></i>
          <span>2. Capture Photo</span>
        </h2>

        <!-- Hidden inputs, driven by the <label for=...> buttons below -->
        <input type="file" id="app-file-input" accept="image/*" bind:this={fileInputRef} onchange={handleFileSelect} multiple class="opacity-0 absolute -z-10 w-10 h-10">
        <input type="file" id="app-camera-input" accept="image/*" bind:this={cameraInputRef} onchange={handleFileSelect} capture="environment" class="opacity-0 absolute -z-10 w-10 h-10">

        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div 
          ondragover={handleDragOver}
          ondragleave={handleDragLeave}
          ondrop={handleDrop}
          class="border-2 border-dashed rounded-xl p-4 transition-all flex flex-col items-center justify-center min-h-[220px] 
            {dropZoneOver ? 'border-[#ff79c6] bg-[#ff79c6]/10' : 'border-[#343746] hover:border-[#ff79c6] bg-[#1e1f29]/60'}"
        >
          {#if base64Images.length === 0}
            <div class="space-y-4 w-full text-center py-4">
              <label for="app-file-input" class="cursor-pointer block space-y-2">
                <i class="fa-solid fa-cloud-arrow-up text-4xl text-[#6272a4]"></i>
                <div>
                  <p class="text-sm font-medium text-[#f8f8f2]">Drag & drop photo(s) here</p>
                  <p class="text-xs text-[#6272a4] mt-1">or click to browse multiple files</p>
                </div>
              </label>
              <div class="flex justify-center space-x-2 pt-2">
                <label for="app-file-input" class="bg-[#343746] hover:bg-[#44475a] text-[#f8f8f2] text-xs px-3 py-1.5 rounded-md border border-[#44475a] transition-colors cursor-pointer inline-flex items-center justify-center">
                  Browse Files
                </label>
                <label for="app-camera-input" class="bg-[#ff79c6] hover:bg-[#ff62ba] text-[#21222c] text-xs font-semibold px-3 py-1.5 rounded-md transition-colors flex items-center space-x-1 cursor-pointer inline-flex shadow">
                  <i class="fa-solid fa-camera"></i>
                  <span>Take Photo</span>
                </label>
              </div>
            </div>
          {:else}
            <div class="w-full space-y-3">
              <!-- Multi-Photo Grid -->
              <div class="grid grid-cols-2 gap-2 max-h-[300px] overflow-y-auto p-1">
                {#each base64Images as img, idx}
                  <div class="relative group rounded-lg overflow-hidden border border-[#343746] bg-[#1e1f29]">
                    <img src={img} alt="Preview {idx + 1}" class="h-28 w-full object-cover">
                    <button 
                      type="button" 
                      onclick={(e) => { e.stopPropagation(); removeImage(idx); }}
                      class="absolute top-1 right-1 bg-[#ff5555] hover:bg-[#ff5555]/80 text-[#f8f8f2] text-xs rounded-full w-6 h-6 flex items-center justify-center shadow-lg transition-colors cursor-pointer"
                      title="Remove photo"
                    >
                      <i class="fa-solid fa-xmark"></i>
                    </button>
                    <div class="absolute bottom-1 left-1 bg-[#21222c]/90 text-[10px] text-[#ff79c6] px-1.5 py-0.5 rounded font-mono font-bold">
                      #{idx + 1}
                    </div>
                  </div>
                {/each}
              </div>

              <!-- Multi-Photo Action Row -->
              <div class="flex items-center justify-between pt-2 border-t border-[#343746] text-xs">
                <span class="text-[#6272a4] font-medium">{base64Images.length} photo{base64Images.length > 1 ? 's' : ''}</span>
                <div class="flex space-x-1.5">
                  <label for="app-file-input" class="bg-[#343746] hover:bg-[#44475a] text-[#f8f8f2] px-2 py-1 rounded border border-[#44475a] cursor-pointer inline-flex items-center space-x-1">
                    <i class="fa-solid fa-plus text-[10px]"></i>
                    <span>Add File</span>
                  </label>
                  <label for="app-camera-input" class="bg-[#343746] hover:bg-[#44475a] text-[#ff79c6] px-2 py-1 rounded border border-[#44475a] cursor-pointer inline-flex items-center space-x-1">
                    <i class="fa-solid fa-camera text-[10px]"></i>
                    <span>Snap</span>
                  </label>
                  <button type="button" onclick={(e) => { e.stopPropagation(); resetImages(); }} class="bg-[#ff5555]/20 hover:bg-[#ff5555]/40 border border-[#ff5555]/40 text-[#ff5555] px-2 py-1 rounded transition-colors cursor-pointer">
                    Clear
                  </button>
                </div>
              </div>
            </div>
          {/if}
        </div>

        <!-- Primary Action Button (Homebox Pink) -->
        <button 
          onclick={analyzePhoto}
          disabled={analyzeBtnDisabled}
          class="w-full bg-[#ff79c6] hover:bg-[#ff62ba] disabled:bg-[#343746] disabled:text-[#6272a4] disabled:cursor-not-allowed text-[#21222c] font-bold py-3 rounded-lg transition-all shadow-md flex items-center justify-center space-x-2 cursor-pointer"
        >
          {#if isAnalyzing}
            <i class="fa-solid fa-spinner animate-spin"></i>
            <span>Analyzing {base64Images.length > 1 ? `${base64Images.length} Photos...` : 'Photo...'}</span>
          {:else}
            <i class="fa-solid fa-wand-magic-sparkles"></i>
            <span>Analyze & Identify Items {base64Images.length > 1 ? `(${base64Images.length} Photos)` : ''}</span>
          {/if}
        </button>
      </div>
    </div>

    <!-- Right Panel: Results & Import (3 Cols) -->
    <div class="lg:col-span-3 space-y-6">
      <div class="bg-[#21222c] border border-[#343746] rounded-2xl p-5 shadow-xl min-h-[400px] flex flex-col justify-between">
        <div>
          <div class="flex justify-between items-center border-b border-[#343746] pb-3 mb-4">
            <h2 class="text-base font-bold text-[#8be9fd] flex items-center space-x-2">
              <i class="fa-solid fa-list-check text-[#ff79c6]"></i>
              <span>3. Review & Import</span>
            </h2>
            <button onclick={addItem} disabled={isAnalyzing} class="bg-[#343746] hover:bg-[#44475a] disabled:opacity-50 disabled:cursor-not-allowed text-xs text-[#f8f8f2] border border-[#44475a] px-2.5 py-1 rounded-md transition-colors cursor-pointer">
              <i class="fa-solid fa-plus mr-1"></i> Add Item
            </button>
          </div>

          <!-- Live Status Loading State -->
          {#if isAnalyzing}
            <div class="flex flex-col items-center justify-center py-10 space-y-5 max-w-md mx-auto">
              <!-- Glowing Brain & Animated Ring -->
              <div class="relative flex items-center justify-center">
                <div class="animate-spin rounded-full h-20 w-20 border-4 border-[#ff79c6]/20 border-t-[#ff79c6]"></div>
                <i class="fa-solid fa-brain text-[#ff79c6] text-2xl absolute animate-pulse"></i>
              </div>

              <!-- Main Status Label & Substatus -->
              <div class="text-center space-y-1">
                <p class="text-base font-semibold text-[#f8f8f2]">{analysisStatus}</p>
                <p class="text-xs text-[#8be9fd] font-mono">{analysisSubStatus}</p>
              </div>

              <!-- Progress Bar -->
              <div class="w-full bg-[#1e1f29] h-2.5 rounded-full overflow-hidden border border-[#343746] shadow-inner">
                <div 
                  class="bg-gradient-to-r from-[#bd93f9] via-[#ff79c6] to-[#50fa7b] h-full transition-all duration-500 ease-out" 
                  style="width: {analysisProgress}%"
                ></div>
              </div>

              <!-- Step Breakdown Timeline -->
              <div class="w-full space-y-2 text-xs bg-[#1e1f29]/80 p-3.5 rounded-xl border border-[#343746]">
                <div class="flex items-center space-x-2.5 {activeStepIndex >= 0 ? 'text-[#ff79c6] font-medium' : 'text-[#6272a4]'}">
                  <i class="fa-solid {activeStepIndex > 0 ? 'fa-circle-check text-[#50fa7b]' : activeStepIndex === 0 ? 'fa-spinner animate-spin text-[#ff79c6]' : 'fa-circle text-[#343746]'} text-[11px]"></i>
                  <span>1. Encode photo payload</span>
                </div>
                <div class="flex items-center space-x-2.5 {activeStepIndex >= 1 ? 'text-[#ff79c6] font-medium' : 'text-[#6272a4]'}">
                  <i class="fa-solid {activeStepIndex > 1 ? 'fa-circle-check text-[#50fa7b]' : activeStepIndex === 1 ? 'fa-spinner animate-spin text-[#ff79c6]' : 'fa-circle text-[#343746]'} text-[11px]"></i>
                  <span>2. Transmit to {selectedProvider === 'gemini' ? 'Google Gemini' : 'Anthropic Claude'}</span>
                </div>
                <div class="flex items-center space-x-2.5 {activeStepIndex >= 2 ? 'text-[#ff79c6] font-medium' : 'text-[#6272a4]'}">
                  <i class="fa-solid {activeStepIndex > 2 ? 'fa-circle-check text-[#50fa7b]' : activeStepIndex === 2 ? 'fa-spinner animate-spin text-[#ff79c6]' : 'fa-circle text-[#343746]'} text-[11px]"></i>
                  <span>3. Detect items & visual features</span>
                </div>
                <div class="flex items-center space-x-2.5 {activeStepIndex >= 3 ? 'text-[#ff79c6] font-medium' : 'text-[#6272a4]'}">
                  <i class="fa-solid {activeStepIndex > 3 ? 'fa-circle-check text-[#50fa7b]' : activeStepIndex === 3 ? 'fa-spinner animate-spin text-[#ff79c6]' : 'fa-circle text-[#343746]'} text-[11px]"></i>
                  <span>4. Catalog names, quantities & tags</span>
                </div>
              </div>
            </div>
          {:else if items.length === 0}
            <!-- Empty State -->
            <div class="flex flex-col items-center justify-center py-16 text-[#6272a4] text-center space-y-3">
              <i class="fa-solid fa-boxes-stacked text-5xl text-[#343746]"></i>
              <div>
                <p class="text-sm font-medium text-[#f8f8f2]">No items detected yet</p>
                <p class="text-xs text-[#6272a4] mt-1">Select a location, capture a photo, and click analyze.</p>
              </div>
            </div>
          {:else}
            <!-- Mobile-First Item Cards (Phone View: sm:hidden) -->
            <div class="sm:hidden space-y-3">
              <div class="flex items-center justify-between px-1 py-1 text-xs text-[#6272a4] border-b border-[#343746]/60 pb-2">
                <label class="flex items-center space-x-2 cursor-pointer text-[#f8f8f2] font-semibold">
                  <input type="checkbox" bind:checked={selectAll} onchange={toggleAll} class="h-4 w-4 rounded bg-[#1e1f29] border-[#343746] text-[#ff79c6] focus:ring-[#ff79c6]">
                  <span>Select All ({items.length})</span>
                </label>
                <span class="text-[#8be9fd]">{selectedCount} selected</span>
              </div>

              {#each items as item (item.id)}
                <div class="bg-[#1e1f29] border border-[#343746] rounded-xl p-3.5 space-y-3 shadow-sm transition-all {item.checked ? 'border-[#ff79c6]/50 bg-[#ff79c6]/5' : ''}">
                  <!-- Card Header: Checkbox + Name + Delete -->
                  <div class="flex items-center space-x-2.5">
                    <input 
                      type="checkbox" 
                      bind:checked={item.checked} 
                      onchange={handleItemCheckboxChange} 
                      class="h-5 w-5 rounded bg-[#21222c] border-[#343746] text-[#ff79c6] focus:ring-[#ff79c6] flex-shrink-0 cursor-pointer"
                    >
                    <input 
                      type="text" 
                      bind:value={item.name} 
                      placeholder="Item name"
                      class="flex-grow bg-[#21222c] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] font-semibold focus:outline-none focus:border-[#ff79c6]"
                    >
                    <button 
                      onclick={() => deleteItem(item.id)} 
                      class="h-9 w-9 flex items-center justify-center text-[#6272a4] hover:text-[#ff5555] bg-[#21222c] border border-[#343746] rounded-lg transition-colors flex-shrink-0 cursor-pointer" 
                      title="Delete item"
                    >
                      <i class="fa-solid fa-trash-can text-sm"></i>
                    </button>
                  </div>

                  <!-- Card Body: Description & Quantity Stepper -->
                  <div class="grid grid-cols-3 gap-2">
                    <div class="col-span-2">
                      <input 
                        type="text" 
                        bind:value={item.description} 
                        placeholder="Description (optional)"
                        class="w-full bg-[#21222c] border border-[#343746] rounded-lg px-3 py-2 text-xs text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]"
                      >
                    </div>
                    <div class="flex items-center border border-[#343746] rounded-lg bg-[#21222c] overflow-hidden">
                      <button 
                        onclick={() => item.quantity = Math.max(1, (parseFloat(String(item.quantity)) || 1) - 1)}
                        class="px-2 py-1 text-[#6272a4] hover:text-[#f8f8f2] text-xs transition-colors cursor-pointer"
                      >
                        -
                      </button>
                      <input 
                        type="number" 
                        step="any" 
                        bind:value={item.quantity} 
                        class="w-full text-center bg-transparent text-xs font-bold text-[#f8f8f2] focus:outline-none"
                      >
                      <button 
                        onclick={() => item.quantity = (parseFloat(String(item.quantity)) || 0) + 1}
                        class="px-2 py-1 text-[#6272a4] hover:text-[#f8f8f2] text-xs transition-colors cursor-pointer"
                      >
                        +
                      </button>
                    </div>
                  </div>
                </div>
              {/each}
            </div>

            <!-- Desktop Data Table (Desktop View: hidden sm:block) -->
            <div class="hidden sm:block overflow-x-auto">
              <table class="w-full text-left border-collapse text-sm">
                <thead>
                  <tr class="border-b border-[#343746] text-[#8be9fd] text-xs uppercase tracking-wider font-semibold">
                    <th class="py-3 px-2 w-8">
                      <input type="checkbox" bind:checked={selectAll} onchange={toggleAll} class="rounded bg-[#1e1f29] border-[#343746] text-[#ff79c6] focus:ring-[#ff79c6]">
                    </th>
                    <th class="py-3 px-3">Item Name</th>
                    <th class="py-3 px-3 w-20 text-center">Qty</th>
                    <th class="py-3 px-3">Description</th>
                    <th class="py-3 px-2 w-10 text-center"></th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-[#343746]/60">
                  {#each items as item (item.id)}
                    <tr class="hover:bg-[#1e1f29]/80 transition-colors border-b border-[#343746]/40">
                      <td class="py-3 px-2 text-center align-middle">
                        <input type="checkbox" bind:checked={item.checked} onchange={handleItemCheckboxChange} class="rounded bg-[#1e1f29] border-[#343746] text-[#ff79c6] focus:ring-[#ff79c6]">
                      </td>
                      <td class="py-2 px-3 align-middle">
                        <input type="text" bind:value={item.name} class="w-full bg-[#1e1f29] border border-[#343746] rounded px-2.5 py-1.5 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]">
                      </td>
                      <td class="py-2 px-3 align-middle text-center">
                        <input type="number" step="any" bind:value={item.quantity} class="w-full text-center bg-[#1e1f29] border border-[#343746] rounded px-1.5 py-1.5 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]">
                      </td>
                      <td class="py-2 px-3 align-middle">
                        <input type="text" bind:value={item.description} class="w-full bg-[#1e1f29] border border-[#343746] rounded px-2.5 py-1.5 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]">
                      </td>
                      <td class="py-2 px-2 align-middle text-center">
                        <button onclick={() => deleteItem(item.id)} class="text-[#6272a4] hover:text-[#ff5555] p-1.5 transition-colors cursor-pointer" title="Delete item">
                          <i class="fa-solid fa-trash-can"></i>
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>

        <!-- Import Actions -->
        {#if items.length > 0}
          <div class="mt-6 pt-4 border-t border-[#343746] space-y-4">
            <div class="flex items-center justify-between text-xs text-[#6272a4]">
              <span>Selected: <strong class="text-[#f8f8f2]">{selectedCount}</strong> items</span>
              <span>Destination: <strong class="text-[#8be9fd]">{selectedLocationName()}</strong></span>
            </div>
            <label class="flex items-center space-x-2 text-xs text-[#f8f8f2] cursor-pointer pt-1">
              <input type="checkbox" bind:checked={attachPhotosToImport} class="rounded bg-[#1e1f29] border-[#343746] text-[#ff79c6] focus:ring-[#ff79c6]">
              <span class="flex items-center space-x-1">
                <i class="fa-solid fa-paperclip text-[#ff79c6]"></i>
                <span>Attach photo(s) to created Homebox items</span>
              </span>
            </label>
            <button 
              onclick={importApprovedItems}
              disabled={importBtnDisabled || selectedCount === 0 || !selectedLocation}
              class="w-full font-bold py-3 rounded-xl transition-all shadow-md flex items-center justify-center space-x-2 cursor-pointer 
                { (importBtnDisabled || selectedCount === 0 || !selectedLocation) ? 'bg-[#343746] text-[#6272a4] cursor-not-allowed' : 'bg-[#50fa7b] hover:bg-[#50fa7b]/90 text-[#21222c]' }"
            >
              {#if importBtnDisabled}
                <i class="fa-solid fa-spinner animate-spin"></i>
                <span>Importing...</span>
              {:else}
                <i class="fa-solid fa-file-import"></i>
                <span>{importBtnText}</span>
              {/if}
            </button>
          </div>
        {/if}
      </div>
    </div>
  </div>
</main>

<!-- Mobile Floating Action Bar (Phone View Only: sm:hidden) -->
<div class="sm:hidden fixed bottom-0 left-0 right-0 z-40 bg-[#21222c]/95 border-t border-[#343746] px-4 py-3 shadow-2xl backdrop-blur-md pb-5 flex items-center space-x-2">
  {#if base64Images.length === 0}
    <label for="app-camera-input" class="flex-grow bg-[#ff79c6] hover:bg-[#ff62ba] text-[#21222c] font-bold py-3 rounded-xl flex items-center justify-center space-x-2 cursor-pointer shadow">
      <i class="fa-solid fa-camera text-base"></i>
      <span>Snap Photo</span>
    </label>
    <label for="app-file-input" class="bg-[#343746] hover:bg-[#44475a] text-[#f8f8f2] px-4 py-3 rounded-xl flex items-center justify-center cursor-pointer border border-[#44475a]">
      <i class="fa-solid fa-folder-open"></i>
    </label>
  {:else if items.length === 0}
    <button 
      onclick={analyzePhoto}
      disabled={analyzeBtnDisabled}
      class="w-full bg-[#ff79c6] hover:bg-[#ff62ba] disabled:bg-[#343746] disabled:text-[#6272a4] disabled:cursor-not-allowed text-[#21222c] font-bold py-3 rounded-xl transition-all shadow-md flex items-center justify-center space-x-2 cursor-pointer"
    >
      {#if isAnalyzing}
        <i class="fa-solid fa-spinner animate-spin"></i>
        <span>Analyzing {base64Images.length} Photo{base64Images.length > 1 ? 's' : ''}...</span>
      {:else}
        <i class="fa-solid fa-wand-magic-sparkles"></i>
        <span>Analyze ({base64Images.length} Photo{base64Images.length > 1 ? 's' : ''})</span>
      {/if}
    </button>
  {:else}
    <button 
      onclick={importApprovedItems}
      disabled={importBtnDisabled || selectedCount === 0 || !selectedLocation}
      class="w-full font-bold py-3 rounded-xl transition-all shadow-md flex items-center justify-center space-x-2 cursor-pointer 
        { (importBtnDisabled || selectedCount === 0 || !selectedLocation) ? 'bg-[#343746] text-[#6272a4] cursor-not-allowed' : 'bg-[#50fa7b] text-[#21222c]' }"
    >
      {#if importBtnDisabled}
        <i class="fa-solid fa-spinner animate-spin"></i>
        <span>Importing...</span>
      {:else}
        <i class="fa-solid fa-file-import"></i>
        <span>Import {selectedCount} Selected Items</span>
      {/if}
    </button>
  {/if}
</div>

<!-- Footer -->
<footer class="bg-[#21222c] border-t border-[#343746] py-4 px-6 text-center text-xs text-[#6272a4]">
  <p>Homebox Vision Importer — Homelab AI Vision Importer</p>
</footer>

<!-- Settings Modal -->
{#if settingsModalOpen}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div 
    onclick={closeSettings}
    class="fixed inset-0 z-50 overflow-y-auto bg-[#282a36]/80 backdrop-blur-sm flex items-center justify-center p-4"
  >
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div 
      onclick={(e) => e.stopPropagation()}
      class="bg-[#21222c] border border-[#343746] rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col"
    >
      <!-- Modal Header -->
      <div class="px-6 py-4 border-b border-[#343746] flex justify-between items-center">
        <h3 class="text-lg font-bold text-[#f8f8f2] flex items-center space-x-2">
          <i class="fa-solid fa-gears text-[#ff79c6]"></i>
          <span>App Configurations</span>
        </h3>
        <button onclick={closeSettings} aria-label="Close settings" class="text-[#6272a4] hover:text-[#f8f8f2] transition-colors cursor-pointer">
          <i class="fa-solid fa-xmark text-xl"></i>
        </button>
      </div>
      
      <!-- Modal Form Body -->
      <div class="p-6 space-y-4 overflow-y-auto max-h-[70vh]">
        <!-- Homebox URL -->
        <div>
          <label for="cfg-url" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Homebox Base URL</label>
          <input 
            type="text" 
            id="cfg-url" 
            bind:value={cfgUrl}
            placeholder="http://localhost:7745" 
            class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]"
          >
          <p class="text-[10px] text-[#6272a4] mt-1">Provide the base URL of your Homebox instance (e.g. <code>http://192.168.1.13:7745</code>).</p>
        </div>

        <!-- Homebox Tenant ID -->
        <div>
          <label for="cfg-tenant" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Homebox Tenant ID (Optional)</label>
          <input 
            type="text" 
            id="cfg-tenant" 
            bind:value={cfgTenant}
            placeholder="e.g. e55161bf-9ac5-45ef-92d4-8c84dd5d076d" 
            class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]"
          >
        </div>

        <!-- Homebox API Key -->
        <div>
          <label for="cfg-token" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Homebox API Key (hb_...)</label>
          <div class="relative">
            <input 
              type={showToken ? "text" : "password"} 
              id="cfg-token" 
              bind:value={cfgToken}
              placeholder="Leave empty to keep existing key" 
              class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg pl-3 pr-10 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]"
            >
            <button type="button" onclick={() => showToken = !showToken} aria-label="Toggle password visibility" class="absolute inset-y-0 right-0 pr-3 flex items-center text-[#6272a4] hover:text-[#f8f8f2] transition-colors cursor-pointer">
              <i class="fa-solid {showToken ? 'fa-eye-slash' : 'fa-eye'}"></i>
            </button>
          </div>
          {#if backendConfig.homebox_api_key}
            <p class="text-[10px] text-[#50fa7b] mt-1">✓ Loaded (ends in: ...{backendConfig.homebox_api_key.slice(-4)})</p>
          {:else}
            <p class="text-[10px] text-[#6272a4] mt-1">✗ No key loaded</p>
          {/if}
        </div>

        <!-- LLM Provider -->
        <div>
          <label for="cfg-provider" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Default AI Provider</label>
          <select id="cfg-provider" bind:value={cfgProvider} class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]">
            <option value="gemini">Google Gemini</option>
            <option value="claude">Anthropic Claude</option>
          </select>
        </div>

        <!-- Gemini API Key -->
        <div>
          <label for="cfg-gemini-key" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Gemini API Key</label>
          <div class="relative">
            <input 
              type={showGeminiKey ? "text" : "password"} 
              id="cfg-gemini-key" 
              bind:value={cfgGeminiKey}
              placeholder="Leave empty to keep existing key" 
              class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg pl-3 pr-10 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]"
            >
            <button type="button" onclick={() => showGeminiKey = !showGeminiKey} aria-label="Toggle password visibility" class="absolute inset-y-0 right-0 pr-3 flex items-center text-[#6272a4] hover:text-[#f8f8f2] transition-colors cursor-pointer">
              <i class="fa-solid {showGeminiKey ? 'fa-eye-slash' : 'fa-eye'}"></i>
            </button>
          </div>
          {#if backendConfig.gemini_api_key}
            <p class="text-[10px] text-[#50fa7b] mt-1">✓ Loaded (ends in: ...{backendConfig.gemini_api_key.slice(-4)})</p>
          {:else}
            <p class="text-[10px] text-[#6272a4] mt-1">✗ No key loaded</p>
          {/if}
        </div>

        <!-- Claude API Key -->
        <div>
          <label for="cfg-claude-key" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Claude API Key</label>
          <div class="relative">
            <input 
              type={showClaudeKey ? "text" : "password"} 
              id="cfg-claude-key" 
              bind:value={cfgClaudeKey}
              placeholder="Leave empty to keep existing key" 
              class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg pl-3 pr-10 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]"
            >
            <button type="button" onclick={() => showClaudeKey = !showClaudeKey} aria-label="Toggle password visibility" class="absolute inset-y-0 right-0 pr-3 flex items-center text-[#6272a4] hover:text-[#f8f8f2] transition-colors cursor-pointer">
              <i class="fa-solid {showClaudeKey ? 'fa-eye-slash' : 'fa-eye'}"></i>
            </button>
          </div>
          {#if backendConfig.anthropic_api_key}
            <p class="text-[10px] text-[#50fa7b] mt-1">✓ Loaded (ends in: ...{backendConfig.anthropic_api_key.slice(-4)})</p>
          {:else}
            <p class="text-[10px] text-[#6272a4] mt-1">✗ No key loaded</p>
          {/if}
        </div>

        <!-- Model configurations (Grid) -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label for="cfg-gemini-model" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Gemini Model</label>
            <input type="text" id="cfg-gemini-model" bind:value={cfgGeminiModel} class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]">
          </div>
          <div>
            <label for="cfg-claude-model" class="block text-xs font-bold text-[#6272a4] uppercase tracking-wider mb-1">Claude Model</label>
            <input type="text" id="cfg-claude-model" bind:value={cfgClaudeModel} class="w-full bg-[#1e1f29] border border-[#343746] rounded-lg px-3 py-2 text-sm text-[#f8f8f2] focus:outline-none focus:border-[#ff79c6]">
          </div>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="px-6 py-4 border-t border-[#343746] bg-[#1e1f29] flex justify-end space-x-3">
        <button onclick={closeSettings} class="bg-[#343746] hover:bg-[#44475a] text-[#f8f8f2] px-4 py-2 rounded-lg text-sm transition-colors cursor-pointer">
          Cancel
        </button>
        <button 
          onclick={saveSettings} 
          disabled={saveSettingsBtnDisabled}
          class="bg-[#ff79c6] hover:bg-[#ff62ba] disabled:bg-[#343746] disabled:text-[#6272a4] text-[#21222c] px-4 py-2 rounded-lg text-sm font-bold transition-colors flex items-center space-x-2 cursor-pointer shadow"
        >
          <i class="fa-solid fa-floppy-disk"></i>
          <span>{saveSettingsBtnText}</span>
        </button>
      </div>
    </div>
  </div>
{/if}
