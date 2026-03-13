// ===== CITADEL LITE — OSINT Dashboard Controller =====
// Vanilla JS — connects to FastAPI backend via REST + SSE.

(function () {
  "use strict";

  // ---------- Config ----------

  var API_BASE = window.location.origin;
  var POLL_MS = 2000;

  // ---------- State ----------

  var currentEventId = null;
  var eventSource = null;
  var pollTimer = null;
  var activeTab = "sentinel";

  var STAGES = ["event", "sentinel", "sherlock", "fixer", "guardian", "execution"];
  var AGENT_KEYS = ["sentinel", "sherlock", "fixer", "guardian", "execution"];
  var SUFFIX = { sentinel: "Sentinel", sherlock: "Sherlock", fixer: "Fixer", guardian: "Guardian", execution: "Execution" };

  // ---------- DOM ----------

  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return document.querySelectorAll(s); };

  var eventForm      = $("#eventForm");
  var submitBtn      = $("#submitBtn");
  var formStatus     = $("#formStatus");
  var pipelineId     = $("#pipelineEventId");
  var agentRegistry  = $("#agentRegistry");
  var reflexRules    = $("#reflexRules");
  var auditChain     = $("#auditChain");
  var memoryEntries  = $("#memoryEntries");

  // Governance
  var riskFill       = $("#riskGaugeFill");
  var riskLabel      = $("#riskGaugeLabel");
  var govDecision    = $("#govDecision");
  var policyRefs     = $("#policyRefs");
  var compStatus     = $("#complianceStatus");

  // KPIs
  var kpiAgents  = $("#kpiAgents");
  var kpiRules   = $("#kpiRules");
  var kpiMode    = $("#kpiMode");
  var kpiLlm     = $("#kpiLlm");
  var kpiStatus  = $("#kpiStatus");
  var footerTime = $("#footerTime");

  // ---------- Init ----------

  document.addEventListener("DOMContentLoaded", function () {
    eventForm.addEventListener("submit", handleSubmit);
    initTabs();
    menuInit();
    loadHealth();
    loadAgents();
    loadRules();
    loadScenarios();
    cfgInit();
    updateClock();
    setInterval(updateClock, 1000);
  });

  function updateClock() {
    if (footerTime) footerTime.textContent = new Date().toLocaleTimeString();
  }

  // ---------- Health / KPIs ----------

  async function loadHealth() {
    try {
      var r = await fetch(API_BASE + "/health");
      if (!r.ok) return;
      var h = await r.json();
      if (kpiAgents) kpiAgents.textContent = h.agents_registered || 0;
      if (kpiRules)  kpiRules.textContent = h.reflex_rules_loaded || 0;
      if (kpiMode)   kpiMode.textContent = (h.execution_mode || "local").toUpperCase();
      if (kpiLlm)    kpiLlm.textContent = h.llm_configured ? "ON" : "OFF";
      if (kpiLlm)    kpiLlm.className = "kpi-value " + (h.llm_configured ? "ok" : "warn");
      if (kpiStatus) { kpiStatus.textContent = "ONLINE"; kpiStatus.className = "kpi-value ok"; }
    } catch (e) {
      if (kpiStatus) { kpiStatus.textContent = "OFFLINE"; kpiStatus.className = "kpi-value err"; }
    }
  }

  // ---------- Tabs ----------

  function initTabs() {
    var tabs = $$("#agentTabs .atab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        switchTab(tab.getAttribute("data-agent"));
      });
    });
  }

  function switchTab(agent) {
    activeTab = agent;
    $$("#agentTabs .atab").forEach(function (t) {
      t.classList.toggle("active", t.getAttribute("data-agent") === agent);
    });
    AGENT_KEYS.forEach(function (k) {
      var el = $("#data" + SUFFIX[k]);
      if (el) el.style.display = (k === agent) ? "block" : "none";
    });
  }

  // ---------- Submit ----------

  async function handleSubmit(e) {
    e.preventDefault();
    submitBtn.disabled = true;
    formStatus.textContent = "SUBMITTING...";

    var repoVal = ($("#eventRepo").value || "").trim();
    var refVal  = ($("#eventRef").value  || "").trim();
    var payload = {
      event_type: $("#eventType").value,
      repo: repoVal || null,
      ref:  refVal  || null,
      summary: $("#eventSummary").value,
      artifacts: { log_excerpt: $("#logExcerpt").value || null }
    };

    try {
      var resp = await fetch(API_BASE + "/webhook/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);

      var data = await resp.json();
      currentEventId = data.event_id;
      formStatus.textContent = "ACCEPTED " + currentEventId.substring(0, 12);
      pipelineId.textContent = "EVENT " + currentEventId;

      resetPipeline();
      updateStage("event", "completed", payload);
      connectSSE(currentEventId);
    } catch (err) {
      formStatus.textContent = "ERR: " + err.message;
    } finally {
      submitBtn.disabled = false;
    }
  }

  // ---------- SSE ----------

  function connectSSE(eventId) {
    if (eventSource) { eventSource.close(); eventSource = null; }
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }

    var url = API_BASE + "/stream/" + eventId;
    try {
      eventSource = new EventSource(url);
      eventSource.onmessage = function (msg) {
        try { handlePipelineEvent(JSON.parse(msg.data)); } catch (e) { /* skip */ }
      };
      eventSource.onerror = function () {
        eventSource.close(); eventSource = null;
        startPolling(eventId);
      };
    } catch (e) {
      startPolling(eventId);
    }
  }

  // ---------- Polling ----------

  function startPolling(eventId) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(function () { pollPipeline(eventId); }, POLL_MS);
    pollPipeline(eventId);
  }

  async function pollPipeline(eventId) {
    try {
      var r = await fetch(API_BASE + "/pipeline/" + eventId);
      if (!r.ok) return;
      processPollData(await r.json());
    } catch (e) { /* retry silently */ }
  }

  function processPollData(d) {
    if (d.handoff_packet) {
      var hp = d.handoff_packet;
      if (hp.agent_outputs) {
        for (var n in hp.agent_outputs) {
          if (hp.agent_outputs.hasOwnProperty(n)) {
            updateStage(n.toLowerCase(), "completed", hp.agent_outputs[n].payload || hp.agent_outputs[n]);
          }
        }
      }
      if (hp.memory_hits && hp.memory_hits.length > 0) renderMemory(hp.memory_hits);
      if (hp.risk) updateGovernance({ risk_score: hp.risk.score });
    }
    if (d.decision) { updateStage("guardian", "completed", d.decision); updateGovernance(d.decision); }
    if (d.execution_outcome) updateStage("execution", "completed", d.execution_outcome);
    if (d.audit_report) renderAuditReport(d.audit_report);
    if (d.execution_outcome || (d.decision && d.decision.action === "block")) {
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }
  }

  // ---------- SSE Handler ----------

  function handlePipelineEvent(evt) {
    if (evt.stage === "keepalive") return;
    updateStage(evt.stage, evt.status, evt.data);

    if (evt.data) {
      if (evt.data.memory_hits) renderMemory(evt.data.memory_hits);
      if (evt.data.risk_score !== undefined) updateGovernance(evt.data);
      if (evt.data.decision) updateGovernance(evt.data.decision);
      if (evt.data.audit_entries) renderAuditEntries(evt.data.audit_entries);
      if (evt.data.hash_chain) renderAuditEntries(evt.data.hash_chain);
    }

    if (evt.stage === "pipeline" && evt.status === "completed") {
      formStatus.textContent = "PIPELINE COMPLETE";
      if (eventSource) { eventSource.close(); eventSource = null; }
      if (currentEventId) pollPipeline(currentEventId);
    }
  }

  // ---------- Pipeline Stages ----------

  function resetPipeline() {
    STAGES.forEach(function (s) {
      var el = document.querySelector('.pstage[data-stage="' + s + '"]');
      if (el) el.removeAttribute("data-status");
    });

    AGENT_KEYS.forEach(function (k) {
      var pre = $("#data" + SUFFIX[k]);
      if (pre) pre.textContent = "Awaiting data...";
      var tab = document.querySelector('.atab[data-agent="' + k + '"]');
      if (tab) tab.classList.remove("has-data");
    });

    if (riskFill) { riskFill.style.width = "0%"; riskFill.style.background = "var(--green)"; }
    if (riskLabel) riskLabel.textContent = "--";
    if (govDecision) { govDecision.textContent = "--"; govDecision.className = "gov-decision"; }
    if (policyRefs) policyRefs.innerHTML = '<li class="muted">No policies evaluated</li>';
    if (compStatus) compStatus.innerHTML = '<span class="cbadge pending">PENDING</span>';
    if (auditChain) auditChain.innerHTML = '<p class="muted">Processing...</p>';
    if (memoryEntries) memoryEntries.innerHTML = '<p class="muted">Searching memory...</p>';
  }

  function updateStage(stage, status, data) {
    // Pipeline bar dot
    var el = document.querySelector('.pstage[data-stage="' + stage + '"]');
    if (el) el.setAttribute("data-status", status);

    // Agent output tab
    var suf = SUFFIX[stage];
    if (suf && data && Object.keys(data).length > 0) {
      var pre = $("#data" + suf);
      if (pre) pre.textContent = fmtJSON(data);

      var tab = document.querySelector('.atab[data-agent="' + stage + '"]');
      if (tab && status === "completed") tab.classList.add("has-data");

      // Auto-switch to this tab when data arrives
      if (status === "completed") switchTab(stage);
    }
  }

  // ---------- Governance ----------

  function updateGovernance(dec) {
    if (!dec) return;

    if (dec.risk_score !== undefined) {
      var s = parseFloat(dec.risk_score);
      var pct = Math.min(Math.max(s * 100, 0), 100);
      if (riskFill) {
        riskFill.style.width = pct + "%";
        riskFill.style.background = s <= 0.3 ? "var(--green)" : s <= 0.6 ? "var(--yellow)" : "var(--red)";
      }
      if (riskLabel) riskLabel.textContent = s.toFixed(2);
    }

    if (dec.action) {
      if (govDecision) {
        govDecision.textContent = dec.action.toUpperCase();
        govDecision.className = "gov-decision " + dec.action;
      }
      var cls = "pending", lbl = "PENDING";
      if (dec.action === "approve") { cls = "compliant"; lbl = "COMPLIANT"; }
      else if (dec.action === "block") { cls = "violation"; lbl = "VIOLATION"; }
      else if (dec.action === "need_approval") { cls = "review"; lbl = "NEEDS REVIEW"; }
      if (compStatus) compStatus.innerHTML = '<span class="cbadge ' + cls + '">' + lbl + '</span>';
    }

    if (dec.policy_refs && dec.policy_refs.length > 0) {
      if (policyRefs) {
        policyRefs.innerHTML = "";
        dec.policy_refs.forEach(function (r) {
          var li = document.createElement("li");
          li.textContent = r;
          policyRefs.appendChild(li);
        });
      }
    }
  }

  // ---------- Audit ----------

  function renderAuditReport(rpt) {
    if (!rpt) return;
    var entries = rpt.hash_chain || rpt.entries || rpt.events || [];
    if (entries.length > 0) renderAuditEntries(entries);
    else { auditChain.innerHTML = ""; auditChain.appendChild(mkAuditEntry("report", new Date().toISOString(), rpt)); }
  }

  function renderAuditEntries(entries) {
    if (!entries || entries.length === 0) return;
    auditChain.innerHTML = "";
    entries.forEach(function (e) {
      auditChain.appendChild(mkAuditEntry(e.stage || e.event || "step", e.timestamp || e.ts || "", e));
    });
  }

  function mkAuditEntry(stage, ts, data) {
    var div = document.createElement("div");
    div.className = "audit-entry";

    var hdr = document.createElement("div");
    hdr.className = "audit-entry-hdr";
    var s = document.createElement("span"); s.className = "audit-stage"; s.textContent = stage;
    hdr.appendChild(s);
    if (ts) { var t = document.createElement("span"); t.className = "audit-ts"; t.textContent = fmtTs(ts); hdr.appendChild(t); }
    div.appendChild(hdr);

    if (data.hash || data.block_hash) {
      var h = document.createElement("div"); h.className = "audit-hash";
      h.textContent = "H: " + (data.hash || data.block_hash);
      div.appendChild(h);
    }
    if (data.prev_hash || data.previous_hash) {
      var p = document.createElement("div"); p.className = "audit-hash";
      p.textContent = "P: " + (data.prev_hash || data.previous_hash);
      div.appendChild(p);
    }

    var det = document.createElement("div"); det.className = "audit-detail";
    var sm = data.summary || data.detail || data.action || "";
    det.textContent = sm || fmtJSON(data);
    div.appendChild(det);

    return div;
  }

  // ---------- Memory ----------

  function renderMemory(hits) {
    if (!hits || hits.length === 0) return;
    memoryEntries.innerHTML = "";
    hits.forEach(function (hit) {
      var card = document.createElement("div");
      card.className = "mem-card";

      var hdr = document.createElement("div");
      hdr.className = "mem-card-hdr";

      var tp = document.createElement("span");
      tp.className = "mem-type";
      tp.textContent = hit.event_type || hit.type || "incident";
      hdr.appendChild(tp);

      if (hit.similarity !== undefined || hit.score !== undefined) {
        var sc = document.createElement("span");
        sc.className = "mem-score";
        sc.textContent = "sim: " + (hit.similarity || hit.score || 0).toFixed(2);
        hdr.appendChild(sc);
      }
      card.appendChild(hdr);

      var sm = document.createElement("div");
      sm.className = "mem-summary";
      sm.textContent = hit.summary || hit.description || fmtJSON(hit);
      card.appendChild(sm);

      memoryEntries.appendChild(card);
    });
  }

  // ---------- Agent Registry ----------

  async function loadAgents() {
    try {
      var r = await fetch(API_BASE + "/agents");
      if (!r.ok) throw new Error("HTTP " + r.status);
      renderAgents(await r.json());
    } catch (e) {
      agentRegistry.innerHTML = '<p class="muted">Could not load agents</p>';
    }
  }

  function renderAgents(agents) {
    if (!agents || agents.length === 0) { agentRegistry.innerHTML = '<p class="muted">No agents</p>'; return; }
    agentRegistry.innerHTML = "";
    agents.forEach(function (a) {
      var card = document.createElement("div");
      card.className = "reg-card";

      var nm = document.createElement("div"); nm.className = "reg-name"; nm.textContent = a.name || a.agent_id;
      card.appendChild(nm);

      var id = document.createElement("div"); id.className = "reg-id"; id.textContent = a.agent_id;
      card.appendChild(id);

      var st = document.createElement("span");
      st.className = "reg-status " + (a.status === "active" ? "active" : "inactive");
      st.textContent = a.status || "unknown";
      card.appendChild(st);

      if (a.capabilities && a.capabilities.length > 0) {
        var ul = document.createElement("ul"); ul.className = "reg-caps";
        a.capabilities.forEach(function (c) {
          var li = document.createElement("li"); li.textContent = c; ul.appendChild(li);
        });
        card.appendChild(ul);
      }

      // Memory / Knowledge Base section
      if (a.memory_hits !== undefined || a.kb_entries !== undefined) {
        var mem = document.createElement("div");
        mem.className = "reg-mem";

        var lbl = document.createElement("div");
        lbl.className = "reg-mem-label";
        lbl.textContent = "KNOWLEDGE BASE";
        mem.appendChild(lbl);

        var hits = document.createElement("div");
        hits.className = "reg-mem-hits";
        var hitCount = (a.memory_hits || 0) + (a.kb_entries || 0);
        hits.textContent = hitCount + " entries";
        mem.appendChild(hits);

        var toggle = document.createElement("button");
        toggle.className = "reg-mem-toggle";
        toggle.textContent = "[inspect]";
        var detail = document.createElement("div");
        detail.className = "reg-mem-detail";
        detail.textContent = a.kb_summary || "Query the Memory menu for full KB data.";
        toggle.addEventListener("click", function () {
          var vis = detail.style.display === "block";
          detail.style.display = vis ? "none" : "block";
          toggle.textContent = vis ? "[inspect]" : "[hide]";
        });
        mem.appendChild(toggle);
        mem.appendChild(detail);
        card.appendChild(mem);
      }

      agentRegistry.appendChild(card);
    });
  }

  // ---------- Reflex Rules ----------

  async function loadRules() {
    try {
      var r = await fetch(API_BASE + "/reflex/rules");
      if (!r.ok) throw new Error("HTTP " + r.status);
      renderRules(await r.json());
    } catch (e) {
      reflexRules.innerHTML = '<p class="muted">Could not load rules</p>';
    }
  }

  function renderRules(rules) {
    if (!rules || rules.length === 0) { reflexRules.innerHTML = '<p class="muted">No rules loaded</p>'; return; }
    reflexRules.innerHTML = "";
    rules.forEach(function (rule) {
      var row = document.createElement("div");
      row.className = "rx-row";

      var id = document.createElement("span"); id.className = "rx-id"; id.textContent = rule.id;
      row.appendChild(id);

      var desc = document.createElement("span"); desc.className = "rx-desc";
      desc.textContent = rule.description || rule.action || "--";
      row.appendChild(desc);

      var trig = document.createElement("span"); trig.className = "rx-trigger";
      trig.textContent = rule.trigger || "--";
      row.appendChild(trig);

      var en = document.createElement("span");
      en.className = "rx-enabled " + (rule.enabled ? "on" : "off");
      en.textContent = rule.enabled ? "ON" : "OFF";
      row.appendChild(en);

      reflexRules.appendChild(row);
    });
  }

  // ---------- Menu Bar ----------

  function menuInit() {
    var backdrop = $("#overlayBackdrop");
    var menuItems = $$(".menu-item");

    menuItems.forEach(function (item) {
      var label = item.querySelector(".menu-label");
      if (label) {
        label.addEventListener("click", function (e) {
          e.stopPropagation();
          var wasOpen = item.classList.contains("open");
          closeAllMenus();
          if (!wasOpen) {
            item.classList.add("open");
            if (backdrop) backdrop.classList.add("active");
          }
        });
      }
    });

    if (backdrop) {
      backdrop.addEventListener("click", function () {
        closeAllMenus();
      });
    }

    // Memory search
    var memSearchBtn = $("#memSearchBtn");
    var memSearchInput = $("#memSearchInput");
    if (memSearchBtn) memSearchBtn.addEventListener("click", memSearch);
    if (memSearchInput) {
      memSearchInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); memSearch(); }
      });
    }
  }

  function closeAllMenus() {
    $$(".menu-item").forEach(function (m) { m.classList.remove("open"); });
    var backdrop = $("#overlayBackdrop");
    if (backdrop) backdrop.classList.remove("active");
  }

  // ---------- Test Scenarios ----------

  var _scenarios = [];

  async function loadScenarios() {
    try {
      var r = await fetch(API_BASE + "/scenarios");
      if (!r.ok) throw new Error("HTTP " + r.status);
      _scenarios = await r.json();
      renderScenarioList(_scenarios);
    } catch (e) {
      var sl = $("#scenarioList");
      if (sl) sl.innerHTML = '<div class="muted">Could not load scenarios</div>';
    }
  }

  function renderScenarioList(scenarios) {
    var sl = $("#scenarioList");
    if (!sl) return;
    sl.innerHTML = "";

    scenarios.forEach(function (sc, idx) {
      var row = document.createElement("div");
      row.className = "scenario-item";
      row.setAttribute("data-idx", idx);

      var tier = document.createElement("span");
      tier.className = "scenario-tier " + (sc._tier || "low");
      tier.textContent = (sc._tier || "low").toUpperCase();
      row.appendChild(tier);

      var label = document.createElement("span");
      label.className = "scenario-label";
      label.textContent = sc._label || sc.summary || sc.event_id;
      row.appendChild(label);

      var type = document.createElement("span");
      type.className = "scenario-type";
      type.textContent = sc.event_type || "--";
      row.appendChild(type);

      row.addEventListener("click", function () {
        loadScenarioIntoForm(sc);
        closeAllMenus();
      });

      sl.appendChild(row);
    });
  }

  function loadScenarioIntoForm(sc) {
    var typeSelect = $("#eventType");
    var summaryInput = $("#eventSummary");
    var logArea = $("#logExcerpt");

    if (typeSelect) typeSelect.value = sc.event_type || "ci_failure";
    if (summaryInput) summaryInput.value = sc.summary || "";
    if (logArea) logArea.value = (sc.artifacts && sc.artifacts.log_excerpt) ? sc.artifacts.log_excerpt : "";

    formStatus.textContent = "SCENARIO LOADED: " + (sc._label || sc.event_id);
  }

  // ---------- Memory / Knowledge Base Search ----------

  async function memSearch() {
    var input = $("#memSearchInput");
    var body = $("#memKbBody");
    var count = $("#memKbCount");
    var q = input ? input.value.trim() : "";

    if (body) body.innerHTML = '<p class="muted">Searching...</p>';

    try {
      var url = API_BASE + "/memory/corpus";
      if (q) url += "?q=" + encodeURIComponent(q);
      var r = await fetch(url);
      if (!r.ok) throw new Error("HTTP " + r.status);
      var hits = await r.json();

      if (count) count.textContent = hits.length;
      renderMemKb(hits, body);
    } catch (e) {
      if (body) body.innerHTML = '<p class="muted">Search failed: ' + e.message + '</p>';
    }
  }

  function renderMemKb(hits, container) {
    if (!container) return;
    container.innerHTML = "";

    if (hits.length === 0) {
      container.innerHTML = '<p class="muted">No matching entries.</p>';
      return;
    }

    hits.forEach(function (h) {
      var item = document.createElement("div");
      item.className = "mem-kb-item";

      var title = document.createElement("div");
      title.className = "mem-kb-title";
      title.textContent = h.title || h.id;
      item.appendChild(title);

      if (h.snippet) {
        var snip = document.createElement("div");
        snip.className = "mem-kb-snippet";
        snip.textContent = h.snippet;
        item.appendChild(snip);
      }

      if (h.tags && h.tags.length > 0) {
        var tags = document.createElement("div");
        tags.className = "mem-kb-tags";
        h.tags.forEach(function (t) {
          var tag = document.createElement("span");
          tag.className = "mem-kb-tag";
          tag.textContent = t;
          tags.appendChild(tag);
        });
        item.appendChild(tags);
      }

      var meta = document.createElement("div");
      meta.className = "mem-kb-meta";
      if (h.confidence !== undefined) {
        var conf = document.createElement("span");
        conf.textContent = "conf: " + h.confidence.toFixed(2);
        meta.appendChild(conf);
      }
      if (h.occurred_at) {
        var ts = document.createElement("span");
        ts.textContent = fmtTs(h.occurred_at);
        meta.appendChild(ts);
      }
      item.appendChild(meta);

      container.appendChild(item);
    });
  }

  // ---------- Configuration Panel ----------

  // Maps HTML element IDs to YAML paths (nested dot notation)
  var CFG_MAP = [
    // Pipeline
    { id: "cfg_pipeline_execution_mode", path: ["pipeline", "execution_mode"], type: "select" },
    { id: "cfg_pipeline_agent_version", path: ["pipeline", "agent_version"], type: "select" },
    { id: "cfg_pipeline_sse_enabled", path: ["pipeline", "sse_enabled"], type: "bool-select" },
    // LLM — Azure OpenAI
    { id: "cfg_llm_azure_openai_endpoint", path: ["llm", "azure_openai", "endpoint"], type: "text" },
    { id: "cfg_llm_azure_openai_api_key", path: ["llm", "azure_openai", "api_key"], type: "text" },
    { id: "cfg_llm_azure_openai_deployment", path: ["llm", "azure_openai", "deployment"], type: "text" },
    // LLM — OpenAI
    { id: "cfg_llm_openai_api_key", path: ["llm", "openai", "api_key"], type: "text" },
    { id: "cfg_llm_openai_model", path: ["llm", "openai", "model"], type: "text" },
    // GitHub
    { id: "cfg_github_token", path: ["github", "token"], type: "text" },
    { id: "cfg_github_webhook_secret", path: ["github", "webhook_secret"], type: "text" },
    // Dashboard
    { id: "cfg_dashboard_enabled", path: ["dashboard", "enabled"], type: "bool-select" },
    { id: "cfg_dashboard_poll_interval_ms", path: ["dashboard", "poll_interval_ms"], type: "number" },
    // Notifications — Slack
    { id: "cfg_notifications_slack_webhook_url", path: ["notifications", "slack", "webhook_url"], type: "text" },
    { id: "cfg_notifications_slack_channel", path: ["notifications", "slack", "channel"], type: "text" },
    // Notifications — Teams
    { id: "cfg_notifications_teams_webhook_url", path: ["notifications", "teams", "webhook_url"], type: "text" },
    // Notifications — Webhook
    { id: "cfg_notifications_webhook_url", path: ["notifications", "webhook", "url"], type: "text" },
    // Azure — Service Bus
    { id: "cfg_azure_service_bus_connection_string", path: ["azure", "service_bus", "connection_string"], type: "text" },
    { id: "cfg_azure_service_bus_queue_name", path: ["azure", "service_bus", "queue_name"], type: "text" },
    // Azure — Cosmos
    { id: "cfg_azure_cosmos_connection_string", path: ["azure", "cosmos", "connection_string"], type: "text" },
    { id: "cfg_azure_cosmos_database", path: ["azure", "cosmos", "database"], type: "text" },
    { id: "cfg_azure_cosmos_container", path: ["azure", "cosmos", "container"], type: "text" },
    // Azure — Foundry
    { id: "cfg_azure_foundry_endpoint", path: ["azure", "foundry", "endpoint"], type: "text" },
    { id: "cfg_azure_foundry_api_key", path: ["azure", "foundry", "api_key"], type: "text" },
    // Azure — App Insights
    { id: "cfg_azure_app_insights_connection_string", path: ["azure", "app_insights", "connection_string"], type: "text" },
    // Azure — Storage
    { id: "cfg_azure_storage_connection_string", path: ["azure", "storage", "connection_string"], type: "text" },
    // Azure — AI Search
    { id: "cfg_azure_ai_search_endpoint", path: ["azure", "ai_search", "endpoint"], type: "text" },
    { id: "cfg_azure_ai_search_api_key", path: ["azure", "ai_search", "api_key"], type: "text" },
    { id: "cfg_azure_ai_search_index_name", path: ["azure", "ai_search", "index_name"], type: "text" },
    // Memory
    { id: "cfg_memory_backend", path: ["memory", "backend"], type: "select" },
    { id: "cfg_memory_faiss_enabled", path: ["memory", "faiss_enabled"], type: "bool-select" },
    // Supabase
    { id: "cfg_supabase_url", path: ["supabase", "url"], type: "text" },
    { id: "cfg_supabase_api_key", path: ["supabase", "api_key"], type: "text" },
    // Notion
    { id: "cfg_notion_api_key", path: ["notion", "api_key"], type: "text" },
    { id: "cfg_notion_database_id", path: ["notion", "database_id"], type: "text" },
    // Slack Bot
    { id: "cfg_slack_bot_token", path: ["slack", "bot_token"], type: "text" },
    { id: "cfg_slack_signing_secret", path: ["slack", "signing_secret"], type: "text" },
  ];

  var cfgSaveBtn = $("#cfgSaveBtn");
  var cfgReloadBtn = $("#cfgReloadBtn");
  var cfgSaveStatus = $("#cfgSaveStatus");

  function cfgInit() {
    if (cfgSaveBtn) cfgSaveBtn.addEventListener("click", cfgSave);
    if (cfgReloadBtn) cfgReloadBtn.addEventListener("click", cfgLoad);
    cfgLoad();
  }

  function cfgGetNested(obj, keys) {
    var cur = obj;
    for (var i = 0; i < keys.length; i++) {
      if (cur === undefined || cur === null || typeof cur !== "object") return "";
      cur = cur[keys[i]];
    }
    return (cur === undefined || cur === null) ? "" : cur;
  }

  function cfgSetNested(obj, keys, val) {
    for (var i = 0; i < keys.length - 1; i++) {
      if (obj[keys[i]] === undefined || typeof obj[keys[i]] !== "object") obj[keys[i]] = {};
      obj = obj[keys[i]];
    }
    obj[keys[keys.length - 1]] = val;
  }

  async function cfgLoad() {
    if (cfgSaveStatus) cfgSaveStatus.textContent = "LOADING...";
    try {
      var r = await fetch(API_BASE + "/config/edit");
      if (!r.ok) throw new Error("HTTP " + r.status);
      var data = await r.json();

      CFG_MAP.forEach(function (m) {
        var el = $("#" + m.id);
        if (!el) return;
        var val = cfgGetNested(data, m.path);

        if (m.type === "bool-select") {
          el.value = (val === true || val === "true") ? "true" : "false";
        } else if (m.type === "number") {
          el.value = val || "";
        } else {
          el.value = val || "";
        }
      });

      if (cfgSaveStatus) cfgSaveStatus.textContent = "LOADED";
      setTimeout(function () { if (cfgSaveStatus) cfgSaveStatus.textContent = ""; }, 2000);
    } catch (e) {
      if (cfgSaveStatus) cfgSaveStatus.textContent = "LOAD FAILED";
    }
  }

  async function cfgSave() {
    if (cfgSaveStatus) cfgSaveStatus.textContent = "SAVING...";

    var payload = {};
    CFG_MAP.forEach(function (m) {
      var el = $("#" + m.id);
      if (!el) return;
      var val = el.value;

      if (m.type === "bool-select") {
        val = (val === "true");
      } else if (m.type === "number") {
        val = parseInt(val, 10) || 0;
      }

      cfgSetNested(payload, m.path, val);
    });

    try {
      var r = await fetch(API_BASE + "/config/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!r.ok) throw new Error("HTTP " + r.status);
      var result = await r.json();

      if (cfgSaveStatus) cfgSaveStatus.textContent = "SAVED";
      setTimeout(function () { if (cfgSaveStatus) cfgSaveStatus.textContent = ""; }, 3000);

      // Refresh KPIs to reflect new config
      loadHealth();
    } catch (e) {
      if (cfgSaveStatus) cfgSaveStatus.textContent = "SAVE FAILED: " + e.message;
    }
  }

  // ---------- Utilities ----------

  function fmtJSON(o) { try { return JSON.stringify(o, null, 2); } catch (e) { return String(o); } }

  function fmtTs(ts) {
    if (!ts) return "";
    try {
      if (typeof ts === "number") return new Date(ts * 1000).toLocaleTimeString();
      return new Date(ts).toLocaleTimeString();
    } catch (e) { return String(ts); }
  }

})();
