/**
 * Smarter.Homes Update Manager — Sidebar Panel v2.1.4
 * Full queue management UI with Add/Edit/Delete + last-scan diagnostics.
 *
 * by Smarter Homes LLC — smarter.homes
 */

import {
  LitElement,
  html,
  css,
} from "https://unpkg.com/lit-element@3.3.3/lit-element.js?module";

class SHUpdateManagerPanel extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      narrow: { type: Boolean },
      panel: { type: Object },
      _queues: { type: Array },
      _loading: { type: Boolean },
      _selectedQueue: { type: Number },
      _showHistory: { type: Boolean },
      _showForm: { type: String },
      _editingQueue: { type: Object },
      _formData: { type: Object },
      _confirmDelete: { type: String },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
        padding: 16px;
        font-family: var(--primary-font-family, Roboto, sans-serif);
        color: var(--primary-text-color);
        background: var(--primary-background-color);
      }
      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 16px;
        flex-wrap: wrap;
        gap: 8px;
      }
      .header h1 {
        margin: 0;
        font-size: 24px;
        font-weight: 500;
      }
      .header-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .btn {
        padding: 8px 16px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        transition: background 0.2s;
      }
      .btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .btn-primary { background: var(--primary-color, #03a9f4); color: white; }
      .btn-primary:hover:not(:disabled) { opacity: 0.9; }
      .btn-danger { background: var(--error-color, #db4437); color: white; }
      .btn-danger:hover:not(:disabled) { opacity: 0.9; }
      .btn-secondary { background: var(--secondary-background-color, #e0e0e0); color: var(--primary-text-color); }
      .btn-success { background: var(--success-color, #4caf50); color: white; }
      .btn-add { background: #7c4dff; color: white; font-size: 15px; }
      .btn-add:hover:not(:disabled) { background: #651fff; }
      .btn-sm { padding: 4px 10px; font-size: 12px; }
      .queue-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
        gap: 16px;
      }
      .queue-card {
        background: var(--card-background-color, white);
        border-radius: 8px;
        padding: 16px;
        box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
        border-left: 4px solid var(--primary-color, #03a9f4);
      }
      .queue-card.running {
        border-left-color: var(--success-color, #4caf50);
      }
      .queue-card.paused {
        border-left-color: var(--warning-color, #ff9800);
      }
      .queue-card.stopped {
        border-left-color: var(--error-color, #db4437);
      }
      .queue-name {
        font-size: 18px; font-weight: 500; margin-bottom: 8px;
        display: flex; align-items: center; justify-content: space-between;
      }
      .queue-name-left { display: flex; align-items: center; gap: 8px; }
      .queue-name-actions { display: flex; gap: 4px; }
      .queue-status {
        font-size: 12px;
        padding: 2px 8px;
        border-radius: 12px;
        text-transform: uppercase;
        font-weight: 600;
      }
      .status-idle { background: #e0e0e0; color: #616161; }
      .status-running { background: #c8e6c9; color: #2e7d32; }
      .status-paused { background: #fff3e0; color: #e65100; }
      .status-stopped { background: #ffcdd2; color: #c62828; }
      .queue-meta {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 4px 16px;
        font-size: 13px;
        color: var(--secondary-text-color);
        margin-bottom: 12px;
      }
      .queue-meta dt { font-weight: 500; }
      .queue-meta dd { margin: 0; }
      .queue-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 8px;
      }
      .queue-actions .btn { padding: 6px 12px; font-size: 13px; }
      .items-list {
        margin-top: 8px;
        max-height: 200px;
        overflow-y: auto;
        font-size: 13px;
      }
      .item-row {
        display: flex;
        justify-content: space-between;
        padding: 4px 0;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }
      .item-status-pending { color: var(--primary-color, #03a9f4); }
      .item-status-installing { color: var(--warning-color, #ff9800); }
      .item-status-completed { color: var(--success-color, #4caf50); }
      .item-status-failed { color: var(--error-color, #db4437); }
      .item-status-skipped { color: var(--secondary-text-color, #757575); }
      .history-section {
        margin-top: 16px;
        padding: 16px;
        background: var(--card-background-color, white);
        border-radius: 8px;
        box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
      }
      .history-run {
        padding: 8px 0;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        font-size: 13px;
      }
      .badge {
        display: inline-block;
        padding: 1px 6px;
        border-radius: 8px;
        font-size: 11px;
        font-weight: 600;
      }
      .badge-battery { background: #fff9c4; color: #f57f17; }
      .empty-state { text-align: center; padding: 48px; color: var(--secondary-text-color); }
      .loading { text-align: center; padding: 48px; }
      .modal-overlay {
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.5); z-index: 1000;
        display: flex; align-items: center; justify-content: center;
      }
      .modal {
        background: var(--card-background-color, white); border-radius: 12px; padding: 24px;
        max-width: 520px; width: 90%; max-height: 85vh; overflow-y: auto;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
      }
      .modal h2 { margin: 0 0 16px; font-size: 20px; font-weight: 500; }
      .form-group { margin-bottom: 14px; }
      .form-group label {
        display: block; font-size: 13px; font-weight: 500;
        margin-bottom: 4px; color: var(--secondary-text-color);
      }
      .form-group input, .form-group select {
        width: 100%; padding: 8px 12px; border: 1px solid var(--divider-color, #ddd);
        border-radius: 4px; font-size: 14px; box-sizing: border-box;
        background: var(--primary-background-color, white); color: var(--primary-text-color);
      }
      .form-group select { cursor: pointer; }
      .form-group input:focus, .form-group select:focus {
        outline: none; border-color: var(--primary-color, #03a9f4);
      }
      .form-group .hint { font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
      .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      .form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
      .confirm-delete {
        background: var(--card-background-color, white); border-radius: 12px; padding: 24px;
        max-width: 400px; width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.3); text-align: center;
      }
      .confirm-delete p { margin: 0 0 20px; font-size: 16px; }
      .confirm-delete .queue-name-highlight { font-weight: 600; color: var(--error-color, #db4437); }
    `;
  }

  constructor() {
    super();
    this._queues = [];
    this._loading = true;
    this._selectedQueue = -1;
    this._showHistory = false;
    this._showForm = "";
    this._editingQueue = null;
    this._formData = this._defaultFormData();
    this._confirmDelete = "";
    this._skippedOpen = new Set();  // slugs with expanded skip-diagnostics
  }

  _defaultFormData() {
    return {
      queue_name: "",
      match_type: "integration",
      match_value: "",
      exec_mode: "sequential",
      trigger_mode: "manual",
      battery_handling: "exclude",
      stop_on_failure: false,
      skip_unavailable: true,
      install_delay: 15,
      install_timeout: 7200,
      max_retries: 2,
      history_count: 25,
      priority: 50,
      exclude_pattern: "",
      resume_after_restart: false,
    };
  }

  connectedCallback() {
    super.connectedCallback();
    this._loadData();
    this._interval = setInterval(() => this._loadData(), 5000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._interval) clearInterval(this._interval);
  }

  async _loadData() {
    if (!this.hass) return;
    try {
      const states = this.hass.states;
      const queues = [];
      const queueEntities = {};

      // Find all queue devices by looking for status sensors
      for (const [entityId, state] of Object.entries(states)) {
        if (!entityId.startsWith("sensor.") || !entityId.includes("update_queue_")) continue;

        // Extract queue slug from entity_id
        const match = entityId.match(/sensor\.update_queue_(.+?)_(status|pending_updates|queue_items|last_run_result|update_history)$/);
        if (!match) continue;

        const slug = match[1];
        const type = match[2];
        if (!queueEntities[slug]) queueEntities[slug] = {};
        queueEntities[slug][type] = state;
      }

      for (const [slug, entities] of Object.entries(queueEntities)) {
        const status = entities.status;
        if (!status) continue;
        const attrs = status.attributes || {};
        const itemsSensor = entities.queue_items;
        const items = itemsSensor?.attributes?.items || [];
        const pendingSensor = entities.pending_updates;
        const lastRunSensor = entities.last_run_result;
        const historySensor = entities.update_history;

        queues.push({
          slug,
          name: (status.attributes?.friendly_name || slug).replace("Update Queue: ", "").replace(" Status", ""),
          state: status.state,
          exec_mode: attrs.exec_mode || "sequential",
          trigger_mode: attrs.trigger_mode || "manual",
          battery_handling: attrs.battery_handling || "exclude",
          priority: attrs.priority || 50,
          match_type: attrs.match_type || "",
          match_value: attrs.match_value || "",
          exclude_pattern: attrs.exclude_pattern || "",
          resume_after_restart: attrs.resume_after_restart === true,
          pending: pendingSensor ? parseInt(pendingSensor.state) || 0 : 0,
          pending_summary: pendingSensor?.attributes?.summary || "",
          completed: pendingSensor?.attributes?.completed || 0,
          failed: pendingSensor?.attributes?.failed || 0,
          items: items,
          last_scan: itemsSensor?.attributes?.last_scan || null,
          last_run: lastRunSensor?.attributes || null,
          last_run_result: lastRunSensor?.state || "idle",
          history_count: historySensor ? parseInt(historySensor.state) || 0 : 0,
          history: historySensor?.attributes?.runs || [],
        });
      }

      queues.sort((a, b) => a.priority - b.priority);
      this._queues = queues;
      this._loading = false;
    } catch (e) {
      console.error("Smarter.Homes Update Manager: error loading data", e);
      this._loading = false;
    }
  }

  async _callService(service, data = {}) {
    try {
      await this.hass.callService("sh_update_manager", service, data);
      setTimeout(() => this._loadData(), 1000);
    } catch (e) {
      console.error("Service call failed:", e);
      alert("Service call failed: " + (e.message || e));
    }
  }

  _scanAll() { this._callService("scan_all"); }
  _stopAll() { this._callService("stop_all"); }
  _scanQueue(name) { this._callService("scan_queue", { queue_name: name }); }
  _startQueue(name) { this._callService("start_queue", { queue_name: name }); }
  _stopQueue(name) { this._callService("stop_queue", { queue_name: name }); }
  _pauseQueue(name) { this._callService("pause_queue", { queue_name: name }); }
  _resumeQueue(name) { this._callService("resume_queue", { queue_name: name }); }
  _skipCurrent(name) { this._callService("skip_current", { queue_name: name }); }
  _retryFailed(name) { this._callService("retry_failed", { queue_name: name }); }

  _toggleHistory(idx) {
    this._selectedQueue = this._selectedQueue === idx ? -1 : idx;
    this._showHistory = this._selectedQueue >= 0;
    this.requestUpdate();
  }

  /* ---- Form management ---- */
  _openAddForm() {
    this._formData = this._defaultFormData();
    this._editingQueue = null;
    this._showForm = "add";
    this.requestUpdate();
  }

  _openEditForm(queue) {
    this._formData = {
      queue_name: queue.name,
      match_type: queue.match_type || "integration",
      match_value: queue.match_value || "",
      exec_mode: queue.exec_mode || "sequential",
      trigger_mode: queue.trigger_mode || "manual",
      battery_handling: queue.battery_handling || "exclude",
      stop_on_failure: false,
      skip_unavailable: true,
      install_delay: 15,
      install_timeout: 7200,
      max_retries: 2,
      history_count: 25,
      priority: queue.priority || 50,
      exclude_pattern: queue.exclude_pattern || "",
      resume_after_restart: queue.resume_after_restart === true,
    };
    this._editingQueue = queue;
    this._showForm = "edit";
    this.requestUpdate();
  }

  _closeForm() {
    this._showForm = "";
    this._editingQueue = null;
    this.requestUpdate();
  }

  _updateFormField(field, value) {
    this._formData = Object.assign({}, this._formData);
    this._formData[field] = value;
    this.requestUpdate();
  }

  async _submitForm() {
    const fd = this._formData;
    if (!fd.queue_name || !fd.queue_name.trim()) {
      alert("Queue name is required.");
      return;
    }
    if (this._showForm === "add") {
      await this._callService("add_queue", {
        queue_name: fd.queue_name.trim(),
        match_type: fd.match_type,
        match_value: fd.match_value,
        exec_mode: fd.exec_mode,
        trigger_mode: fd.trigger_mode,
        battery_handling: fd.battery_handling,
        stop_on_failure: fd.stop_on_failure,
        skip_unavailable: fd.skip_unavailable,
        install_delay: parseInt(fd.install_delay) || 15,
        install_timeout: parseInt(fd.install_timeout) || 7200,
        max_retries: parseInt(fd.max_retries) || 2,
        history_count: parseInt(fd.history_count) || 25,
        priority: parseInt(fd.priority) || 50,
        exclude_pattern: fd.exclude_pattern || "",
        resume_after_restart: fd.resume_after_restart === true,
      });
    } else if (this._showForm === "edit" && this._editingQueue) {
      const data = { queue_name: this._editingQueue.name };
      if (fd.queue_name.trim() !== this._editingQueue.name) {
        data.new_name = fd.queue_name.trim();
      }
      data.match_type = fd.match_type;
      data.match_value = fd.match_value;
      data.exec_mode = fd.exec_mode;
      data.trigger_mode = fd.trigger_mode;
      data.battery_handling = fd.battery_handling;
      data.priority = parseInt(fd.priority) || 50;
      data.exclude_pattern = fd.exclude_pattern || "";
      data.resume_after_restart = fd.resume_after_restart === true;
      await this._callService("edit_queue", data);
    }
    this._closeForm();
    // Reload page after delay so HA can process the config change
    setTimeout(() => window.location.reload(), 3000);
  }

  _openDeleteConfirm(queueName) {
    this._confirmDelete = queueName;
    this.requestUpdate();
  }

  _closeDeleteConfirm() {
    this._confirmDelete = "";
    this.requestUpdate();
  }

  async _confirmDeleteQueue() {
    if (this._confirmDelete) {
      await this._callService("delete_queue", { queue_name: this._confirmDelete });
      this._confirmDelete = "";
      setTimeout(() => window.location.reload(), 3000);
    }
  }

  /* ---- Rendering ---- */
  _renderItem(item) {
    return html`
      <div class="item-row">
        <span>
          ${item.friendly_name || item.entity_id}
          ${item.is_battery ? html`<span class="badge badge-battery">Battery</span>` : ""}
        </span>
        <span>
          <span class="item-status-${item.status}">${item.status}</span>
          ${item.installed_version && item.latest_version
            ? html` <small>${item.installed_version} &rarr; ${item.latest_version}</small>`
            : ""}
          ${item.error ? html`<br><small style="color:var(--error-color)">${item.error}</small>` : ""}
        </span>
      </div>
    `;
  }

  _renderQueue(queue, idx) {
    return html`
      <div class="queue-card ${queue.state}">
        <div class="queue-name">
          <span class="queue-name-left">
            ${queue.name}
            <span class="queue-status status-${queue.state}">${queue.state}</span>
          </span>
          <span class="queue-name-actions">
            <button class="btn btn-secondary btn-sm"
              @click=${() => this._openEditForm(queue)}
              title="Edit queue settings">&#9998; Edit</button>
            <button class="btn btn-danger btn-sm"
              @click=${() => this._openDeleteConfirm(queue.name)}
              title="Delete this queue">&times; Delete</button>
          </span>
        </div>
        <dl class="queue-meta">
          <dt>Priority</dt><dd>${queue.priority}</dd>
          <dt>Mode</dt><dd>${queue.exec_mode}</dd>
          <dt>Trigger</dt><dd>${queue.trigger_mode}</dd>
          <dt>Battery</dt><dd>${queue.battery_handling}</dd>
          <dt>Resume</dt><dd>${queue.resume_after_restart ? "after restart" : "manual"}</dd>
          <dt>Match</dt><dd>${queue.match_type}: ${queue.match_value || "(all)"}${queue.exclude_pattern ? html` <span style="color:var(--error-color,#db4437)">excl: ${queue.exclude_pattern}</span>` : ""}</dd>
          <dt>Pending</dt><dd>${queue.pending_summary || queue.pending}</dd>
          <dt>Last Run</dt><dd>${queue.last_run_result}</dd>
        </dl>

        <div class="queue-actions">
          <button class="btn btn-primary" @click=${() => this._scanQueue(queue.name)}>Scan</button>
          ${queue.state === "idle" || queue.state === "stopped"
            ? html`<button class="btn btn-success" @click=${() => this._startQueue(queue.name)}>Start</button>`
            : ""}
          ${queue.state === "running"
            ? html`
              <button class="btn btn-secondary" @click=${() => this._pauseQueue(queue.name)}>Pause</button>
              <button class="btn btn-danger" @click=${() => this._stopQueue(queue.name)}>Stop</button>
              <button class="btn btn-secondary" @click=${() => this._skipCurrent(queue.name)}>Skip</button>
            ` : ""}
          ${queue.state === "paused"
            ? html`<button class="btn btn-success" @click=${() => this._resumeQueue(queue.name)}>Resume</button>`
            : ""}
          ${queue.failed > 0
            ? html`<button class="btn btn-danger" @click=${() => this._retryFailed(queue.name)}>Retry Failed (${queue.failed})</button>`
            : ""}
          <button class="btn btn-secondary" @click=${() => this._toggleHistory(idx)}>
            History (${queue.history_count})
          </button>
          ${this._skippedCount(queue) > 0 ? html`
            <button class="btn btn-secondary"
              title="Show update entities that matched this queue but were skipped on the last scan"
              @click=${() => this._toggleSkipped(queue.slug)}>
              ${this._skippedOpen.has(queue.slug) ? "Hide" : "Why skipped?"}
              (${this._skippedCount(queue)})
            </button>
          ` : ""}
        </div>

        ${queue.items.length > 0 ? html`
          <div class="items-list">
            ${queue.items.map(item => this._renderItem(item))}
          </div>
        ` : ""}

        ${this._skippedOpen.has(queue.slug) ? this._renderSkipped(queue) : ""}
      </div>
    `;
  }

  _skippedCount(queue) {
    const list = queue?.last_scan?.skipped;
    return Array.isArray(list) ? list.length : 0;
  }

  _renderSkipped(queue) {
    const scan = queue.last_scan || {};
    const list = Array.isArray(scan.skipped) ? scan.skipped : [];
    const counts = scan.counts || {};
    const scannedAt = scan.at ? new Date(scan.at).toLocaleString() : "never";
    return html`
      <div class="history-section">
        <h3>Why skipped — ${queue.name}</h3>
        <p style="margin:0 0 8px; color:var(--secondary-text-color)">
          Last scan: ${scannedAt} &middot; candidates kept: ${scan.candidates ?? 0}
          ${Object.keys(counts).length ? html`
            <br>Skipped totals:
            ${Object.entries(counts)
              .filter(([, v]) => v > 0)
              .map(([k, v]) => `${k}=${v}`)
              .join(", ") || "none"}
          ` : ""}
        </p>
        ${list.length === 0 ? html`<p>No skipped entities on the last scan.</p>` : html`
          <table style="width:100%; border-collapse:collapse; font-size:13px">
            <thead>
              <tr style="text-align:left; border-bottom:1px solid var(--divider-color, #e0e0e0)">
                <th style="padding:4px 6px">Entity</th>
                <th style="padding:4px 6px">Platform</th>
                <th style="padding:4px 6px">Reason</th>
                <th style="padding:4px 6px">Detail</th>
              </tr>
            </thead>
            <tbody>
              ${list.map(row => html`
                <tr style="border-bottom:1px solid var(--divider-color, #eee)">
                  <td style="padding:4px 6px">
                    <div>${row.friendly_name || row.entity_id}</div>
                    <small style="color:var(--secondary-text-color)">${row.entity_id}</small>
                  </td>
                  <td style="padding:4px 6px">${row.platform || ""}</td>
                  <td style="padding:4px 6px"><code>${row.reason}</code></td>
                  <td style="padding:4px 6px; color:var(--secondary-text-color)">${row.note || ""}</td>
                </tr>
              `)}
            </tbody>
          </table>
        `}
      </div>
    `;
  }

  _renderHistory() {
    if (this._selectedQueue < 0 || this._selectedQueue >= this._queues.length) return "";
    const queue = this._queues[this._selectedQueue];
    if (!queue.history || queue.history.length === 0) {
      return html`<div class="history-section"><p>No run history yet.</p></div>`;
    }
    return html`
      <div class="history-section">
        <h3>Run History: ${queue.name}</h3>
        ${queue.history.map(run => html`
          <div class="history-run">
            <strong>Run #${run.run_id}</strong> — ${run.result}
            ${run.duration ? html` (${run.duration})` : ""}
            <br>
            <small>
              ${run.succeeded} succeeded, ${run.failed} failed, ${run.skipped} skipped
              ${run.started ? html` | Started: ${new Date(run.started).toLocaleString()}` : ""}
            </small>
            ${run.failed_items?.length > 0 ? html`
              <div style="margin-top:4px;color:var(--error-color)">
                Failed: ${run.failed_items.map(f => f.friendly_name || f.entity_id).join(", ")}
              </div>
            ` : ""}
          </div>
        `)}
      </div>
    `;
  }

  _renderFormModal() {
    if (!this._showForm) return "";
    const isEdit = this._showForm === "edit";
    const fd = this._formData;
    return html`
      <div class="modal-overlay" @click=${(e) => { if (e.target === e.currentTarget) this._closeForm(); }}>
        <div class="modal">
          <h2>${isEdit ? "Edit Queue" : "Add New Queue"}</h2>

          <div class="form-group">
            <label>Queue Name *</label>
            <input type="text" .value=${fd.queue_name}
              @input=${(e) => this._updateFormField("queue_name", e.target.value)}
              placeholder="e.g. Z-Wave Firmware" />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Match Type</label>
              <select .value=${fd.match_type}
                @change=${(e) => this._updateFormField("match_type", e.target.value)}>
                <option value="integration">Integration</option>
                <option value="area">Area</option>
                <option value="label">Label</option>
                <option value="entity">Entity</option>
                <option value="device_name">Device Name</option>
                <option value="manufacturer">Manufacturer</option>
              </select>
              <div class="hint">How to find update entities for this queue</div>
            </div>
            <div class="form-group">
              <label>Match Values</label>
              <input type="text" .value=${fd.match_value}
                @input=${(e) => this._updateFormField("match_value", e.target.value)}
                placeholder=${fd.match_type === "device_name" ? "e.g. Zooz,ZEN71" : fd.match_type === "manufacturer" ? "e.g. Zooz,Inovelli" : "e.g. zwave_js,zwave"} />
              <div class="hint">${fd.match_type === "device_name" ? "Partial match against device name and model (comma-separated)" : fd.match_type === "manufacturer" ? "Exact manufacturer name (comma-separated)" : "Comma-separated integration names, areas, labels, or entity IDs"}</div>
            </div>
          </div>

          <div class="form-group">
            <label>Exclude Pattern (optional)</label>
            <input type="text" .value=${fd.exclude_pattern}
              @input=${(e) => this._updateFormField("exclude_pattern", e.target.value)}
              placeholder="e.g. ZEN32,Inovelli" />
            <div class="hint">Comma-separated patterns to exclude. Matched against device name, manufacturer, model, and entity ID. Leave empty to include all matched devices.</div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Execution Mode</label>
              <select .value=${fd.exec_mode}
                @change=${(e) => this._updateFormField("exec_mode", e.target.value)}>
                <option value="sequential">Sequential (one at a time)</option>
                <option value="parallel">Parallel (all at once)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Trigger Mode</label>
              <select .value=${fd.trigger_mode}
                @change=${(e) => this._updateFormField("trigger_mode", e.target.value)}>
                <option value="manual">Manual (press Start)</option>
                <option value="auto_on_scan">Auto on Scan</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Battery Handling</label>
              <select .value=${fd.battery_handling}
                @change=${(e) => this._updateFormField("battery_handling", e.target.value)}>
                <option value="exclude">Exclude battery devices</option>
                <option value="defer_to_end">Include - defer to end</option>
                <option value="include">Include - mixed in</option>
              </select>
            </div>
            <div class="form-group">
              <label>Priority (1-100)</label>
              <input type="number" min="1" max="100" .value=${String(fd.priority)}
                @input=${(e) => this._updateFormField("priority", e.target.value)} />
              <div class="hint">Lower = runs first when running all queues</div>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>After a Restart</label>
              <select .value=${fd.resume_after_restart ? "true" : "false"}
                @change=${(e) => this._updateFormField("resume_after_restart", e.target.value === "true")}>
                <option value="false">Stay idle until started</option>
                <option value="true">Resume an interrupted run</option>
              </select>
              <div class="hint">What to do with a run that a Home Assistant restart cut short</div>
            </div>
          </div>

          <details style="margin-top: 8px;">
            <summary style="cursor:pointer; font-size:13px; color:var(--secondary-text-color);">
              Advanced Settings
            </summary>
            <div style="margin-top: 12px;">
              <div class="form-row">
                <div class="form-group">
                  <label>Install Delay (seconds)</label>
                  <input type="number" min="0" max="300" .value=${String(fd.install_delay)}
                    @input=${(e) => this._updateFormField("install_delay", e.target.value)} />
                  <div class="hint">Wait between each install (0-300s)</div>
                </div>
                <div class="form-group">
                  <label>Install Timeout (seconds)</label>
                  <input type="number" min="60" max="14400" .value=${String(fd.install_timeout)}
                    @input=${(e) => this._updateFormField("install_timeout", e.target.value)} />
                  <div class="hint">Max wait per device (60-14400s)</div>
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>Max Retries</label>
                  <input type="number" min="0" max="10" .value=${String(fd.max_retries)}
                    @input=${(e) => this._updateFormField("max_retries", e.target.value)} />
                </div>
                <div class="form-group">
                  <label>History Count</label>
                  <input type="number" min="1" max="100" .value=${String(fd.history_count)}
                    @input=${(e) => this._updateFormField("history_count", e.target.value)} />
                  <div class="hint">Past runs to keep per queue</div>
                </div>
              </div>
            </div>
          </details>

          <div class="form-actions">
            <button class="btn btn-secondary" @click=${() => this._closeForm()}>Cancel</button>
            <button class="btn btn-primary" @click=${() => this._submitForm()}>
              ${isEdit ? "Save Changes" : "Create Queue"}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  _renderDeleteConfirm() {
    if (!this._confirmDelete) return "";
    return html`
      <div class="modal-overlay" @click=${(e) => { if (e.target === e.currentTarget) this._closeDeleteConfirm(); }}>
        <div class="confirm-delete">
          <p>Are you sure you want to delete queue
            <span class="queue-name-highlight">"${this._confirmDelete}"</span>?</p>
          <p style="font-size:13px; color:var(--secondary-text-color);">
            This will remove the queue and all its settings. Update history will be lost.
          </p>
          <div style="display:flex; gap:8px; justify-content:center;">
            <button class="btn btn-secondary" @click=${() => this._closeDeleteConfirm()}>Cancel</button>
            <button class="btn btn-danger" @click=${() => this._confirmDeleteQueue()}>Delete Queue</button>
          </div>
        </div>
      </div>
    `;
  }

  render() {
    if (this._loading) {
      return html`<div class="loading">Loading queues...</div>`;
    }
    return html`
      <div class="header">
        <h1>Smarter.Homes Update Manager</h1>
        <div class="header-actions">
          <button class="btn btn-add" @click=${() => this._openAddForm()}>+ Add Queue</button>
          <button class="btn btn-primary" @click=${this._scanAll}>Scan All Queues</button>
          <button class="btn btn-danger" @click=${this._stopAll}>Stop All</button>
          <button class="btn btn-secondary" @click=${() => this._loadData()}>Refresh</button>
        </div>
      </div>

      ${this._queues.length === 0
        ? html`
          <div class="empty-state">
            <p>No queues configured yet.</p>
            <p>Click <strong>"+ Add Queue"</strong> above to create your first update queue.</p>
          </div>
        `
        : html`
          <div class="queue-grid">
            ${this._queues.map((q, i) => this._renderQueue(q, i))}
          </div>
          ${this._showHistory ? this._renderHistory() : ""}
        `
      }

      ${this._renderFormModal()}
      ${this._renderDeleteConfirm()}
    `;
  }
}

customElements.define("sh-update-manager-panel", SHUpdateManagerPanel);
