const state = {
  health: null,
  documents: [],
  selectedDocumentIds: new Set(),
  activeDocumentId: null,
  activeDocumentDetail: null,
  latestAnswer: null,
};

function q(selector) {
  return document.querySelector(selector);
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : JSON.stringify(payload.detail || payload);
    throw new Error(detail);
  }
  return payload;
}

function renderHealth() {
  const health = state.health;
  q("#retrieval-backend").textContent = health?.retrieval_backend || "Unavailable";
  q("#active-answer-provider").textContent = health?.active_answer_provider || "Unavailable";
}

function buildDocumentRow(documentItem) {
  const row = window.document.createElement("article");
  row.className = "document-row";
  row.innerHTML = `
    <header>
      <div>
        <label class="doc-check">
          <input type="checkbox" ${state.selectedDocumentIds.has(documentItem.document_id) ? "checked" : ""} />
          <div>
            <h4>${escapeHtml(documentItem.filename)}</h4>
            <div class="document-meta">
              <span>${escapeHtml(documentItem.parser)}</span>
              <span>${documentItem.chunk_count} chunks</span>
              <span>${formatDate(documentItem.created_at)}</span>
            </div>
          </div>
        </label>
      </div>
    </header>
    <p class="document-preview">${escapeHtml(documentItem.text_preview || "No preview available.")}</p>
    <div class="document-actions">
      <button type="button" class="secondary" data-action="inspect">Inspect</button>
      <button type="button" class="secondary" data-action="reindex">Reindex</button>
      <button type="button" class="danger" data-action="delete">Delete</button>
    </div>
  `;

  const checkbox = row.querySelector("input[type=checkbox]");
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) {
      state.selectedDocumentIds.add(documentItem.document_id);
    } else {
      state.selectedDocumentIds.delete(documentItem.document_id);
    }
    renderDocuments();
  });

  row.querySelector('[data-action="inspect"]').addEventListener("click", () => loadDocumentDetail(documentItem.document_id));
  row.querySelector('[data-action="reindex"]').addEventListener("click", () => reindexDocument(documentItem.document_id));
  row.querySelector('[data-action="delete"]').addEventListener("click", () => deleteDocument(documentItem.document_id, documentItem.filename));
  return row;
}

function renderDocumentRows() {
  const list = q("#document-list");
  if (state.documents.length === 0) {
    list.innerHTML = '<div class="empty-state">No documents indexed yet.</div>';
    return;
  }
  list.innerHTML = "";
  for (const item of state.documents) {
    list.appendChild(buildDocumentRow(item));
  }
}

function renderDocumentDetail() {
  const target = q("#document-detail");
  const detail = state.activeDocumentDetail;
  if (!detail) {
    target.innerHTML = "<p>Select a document to inspect metadata and chunk preview.</p>";
    return;
  }

  const chunkPreview = detail.chunk_preview
    .map(
      (chunk) => `
        <div class="citation-card">
          <h4>${escapeHtml(chunk.citation_label)}</h4>
          <div class="citation-meta">
            <span>${escapeHtml(chunk.locator)}</span>
            <span>${chunk.start_offset}-${chunk.end_offset}</span>
          </div>
          <p class="citation-snippet">${escapeHtml(chunk.text)}</p>
        </div>
      `,
    )
    .join("");

  target.innerHTML = `
    <h4>${escapeHtml(detail.document.filename)}</h4>
    <div class="detail-meta">
      <span>${escapeHtml(detail.document.parser)}</span>
      <span>${detail.document.chunk_count} chunks</span>
      <span>${formatDate(detail.document.created_at)}</span>
    </div>
    <p class="document-preview">${escapeHtml(detail.document.text_preview)}</p>
    <div class="citation-list">${chunkPreview || '<div class="empty-state">No chunk preview available.</div>'}</div>
  `;
}

function renderAnswer() {
  const response = state.latestAnswer;
  q("#answer-mode").textContent = response?.answer?.mode || "No answer yet";
  q("#answer-provider").textContent = response?.answer_provider_used || "Provider unknown";
  q("#answer-text").textContent = response?.answer?.text || "Upload a document and ask a question to begin.";
  q("#answer-note").textContent = response?.answer?.note || "";

  const citationsTarget = q("#citation-list");
  const sourcesTarget = q("#source-documents");
  if (!response) {
    citationsTarget.innerHTML = '<div class="empty-state">Citations will appear after a question is answered.</div>';
    sourcesTarget.innerHTML = '<div class="empty-state">Source documents will appear after a question is answered.</div>';
    return;
  }

  const previewByChunkId = new Map(response.retrieval_preview.map((item) => [item.chunk_id, item]));
  citationsTarget.innerHTML = response.citations
    .map((citation) => {
      const preview = previewByChunkId.get(citation.chunk_id);
      return `
        <article class="citation-card">
          <h4>${escapeHtml(citation.filename)}</h4>
          <div class="citation-meta">
            <span>${escapeHtml(citation.citation_label)}</span>
            <span>${preview ? `score ${preview.score}` : ""}</span>
          </div>
          <p class="citation-snippet">${escapeHtml(preview?.excerpt || citation.locator)}</p>
        </article>
      `;
    })
    .join("");

  sourcesTarget.innerHTML = response.source_documents
    .map(
      (documentItem) => `
        <article class="source-card">
          <h4>${escapeHtml(documentItem.filename)}</h4>
          <div class="source-meta">
            <span>${escapeHtml(documentItem.parser)}</span>
            <span>${formatDate(documentItem.created_at)}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

async function loadHealth() {
  state.health = await request("/health");
  renderHealth();
}

async function loadDocuments() {
  const response = await request("/documents");
  state.documents = response.documents;
  state.selectedDocumentIds = new Set(
    [...state.selectedDocumentIds].filter((documentId) => state.documents.some((item) => item.document_id === documentId)),
  );
  renderDocumentRows();
  q("#document-count").textContent = `${response.documents_count} indexed`;
  q("#selection-state").textContent =
    state.selectedDocumentIds.size > 0
      ? `${state.selectedDocumentIds.size} selected`
      : "All indexed documents";
}

async function loadDocumentDetail(documentId) {
  state.activeDocumentId = documentId;
  state.activeDocumentDetail = await request(`/documents/${documentId}`);
  renderDocumentDetail();
}

async function uploadDocument(event) {
  event.preventDefault();
  const status = q("#upload-status");
  const input = q("#upload-file");
  const file = input.files?.[0];
  if (!file) {
    status.textContent = "Choose a file first.";
    return;
  }

  status.textContent = "Uploading and indexing...";
  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await request("/documents/upload", { method: "POST", body: formData });
    status.textContent = response.note;
    input.value = "";
    await loadHealth();
    await loadDocuments();
  } catch (error) {
    status.textContent = `Upload failed: ${error.message}`;
  }
}

async function resetDemoState() {
  q("#upload-status").textContent = "Resetting demo state...";
  try {
    const response = await request("/demo/reset", { method: "POST" });
    state.documents = [];
    state.selectedDocumentIds = new Set();
    state.activeDocumentId = null;
    state.activeDocumentDetail = null;
    state.latestAnswer = null;
    renderDocumentRows();
    renderDocumentDetail();
    renderAnswer();
    await loadHealth();
    await loadDocuments();
    q("#upload-status").textContent = response.note;
  } catch (error) {
    q("#upload-status").textContent = `Reset failed: ${error.message}`;
  }
}

async function loadSamplePack() {
  q("#upload-status").textContent = "Loading JVT sample pack...";
  try {
    const response = await request("/demo/sample-pack", { method: "POST" });
    await loadHealth();
    await loadDocuments();
    q("#upload-status").textContent = response.note;
  } catch (error) {
    q("#upload-status").textContent = `Sample-pack load failed: ${error.message}`;
  }
}

async function askQuestion(event) {
  event.preventDefault();
  const question = q("#question-input").value.trim();
  if (!question) {
    q("#question-status").textContent = "Enter a question first.";
    return;
  }

  const payload = { question };
  if (state.selectedDocumentIds.size > 0) {
    payload.document_ids = [...state.selectedDocumentIds];
  }
  const selectedProvider = q("#provider-select").value;
  if (selectedProvider) {
    payload.answer_provider = selectedProvider;
  }

  q("#question-status").textContent = "Generating grounded answer...";
  try {
    state.latestAnswer = await request("/questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    q("#question-status").textContent = "Answer generated.";
    renderAnswer();
  } catch (error) {
    q("#question-status").textContent = `Question failed: ${error.message}`;
  }
}

async function deleteDocument(documentId, filename) {
  if (!window.confirm(`Delete ${filename} from local demo storage?`)) {
    return;
  }
  q("#upload-status").textContent = `Deleting ${filename}...`;
  try {
    await request(`/documents/${documentId}`, { method: "DELETE" });
    if (state.activeDocumentId === documentId) {
      state.activeDocumentId = null;
      state.activeDocumentDetail = null;
      renderDocumentDetail();
    }
    state.selectedDocumentIds.delete(documentId);
    await loadHealth();
    await loadDocuments();
    q("#upload-status").textContent = `${filename} deleted from local demo storage.`;
  } catch (error) {
    q("#upload-status").textContent = `Delete failed: ${error.message}`;
  }
}

async function reindexDocument(documentId) {
  q("#upload-status").textContent = "Reindexing document...";
  try {
    const response = await request(`/documents/${documentId}/reindex`, { method: "POST" });
    await loadHealth();
    await loadDocuments();
    await loadDocumentDetail(documentId);
    q("#upload-status").textContent = response.note;
  } catch (error) {
    q("#upload-status").textContent = `Reindex failed: ${error.message}`;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDate(value) {
  try {
    return new Date(value).toLocaleString();
  } catch (_) {
    return value;
  }
}

function bindQuestionPresets() {
  window.document.querySelectorAll(".preset-question").forEach((button) => {
    button.addEventListener("click", () => {
      q("#question-input").value = button.dataset.question || "";
      q("#question-input").focus();
    });
  });
}

async function init() {
  q("#upload-form").addEventListener("submit", uploadDocument);
  q("#question-form").addEventListener("submit", askQuestion);
  q("#reset-demo-btn").addEventListener("click", resetDemoState);
  q("#load-sample-pack-btn").addEventListener("click", loadSamplePack);
  bindQuestionPresets();
  await loadHealth();
  await loadDocuments();
  renderDocumentDetail();
  renderAnswer();
}

init().catch((error) => {
  q("#question-status").textContent = `Startup failed: ${error.message}`;
});
