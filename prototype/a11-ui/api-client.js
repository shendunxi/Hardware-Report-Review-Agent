(function () {
  class ApiError extends Error {
    constructor(status, payload) {
      const error = payload && payload.error ? payload.error : {};
      super(error.message || `请求失败（HTTP ${status}）`);
      this.name = 'ApiError';
      this.status = status;
      this.code = error.code || 'HTTP_ERROR';
      this.details = error.details || {};
    }
  }

  class ApiClient {
    constructor(options = {}) {
      this.baseUrl = String(options.baseUrl || '').replace(/\/$/, '');
      this.fetch = options.fetchImpl || window.fetch.bind(window);
      this.FormData = options.FormDataImpl || window.FormData;
    }

    async request(path, options = {}) {
      const response = await this.fetch(`${this.baseUrl}${path}`, options);
      const payload = response.status === 204 ? null : await response.json();
      if (!response.ok) throw new ApiError(response.status, payload);
      return payload;
    }

    createTask({ templateId, primaryReport, supportingFiles = [] }) {
      if (!templateId) throw new TypeError('templateId is required');
      if (!primaryReport) throw new TypeError('primaryReport is required');
      const form = new this.FormData();
      form.append('template_id', templateId);
      form.append('primary_report', primaryReport);
      supportingFiles.forEach(item => form.append('supporting_files', item.file));
      form.append('supporting_manifest', JSON.stringify(supportingFiles.map(item => ({
        evidence_kinds: Array.from(item.evidenceKinds || [])
      }))));
      return this.request('/api/tasks', { method: 'POST', body: form });
    }

    executeTask(taskId) {
      return this.request(`/api/tasks/${encodeURIComponent(taskId)}/execute`, { method: 'POST' });
    }

    listTasks() {
      return this.request('/api/tasks');
    }

    getTask(taskId) {
      return this.request(`/api/tasks/${encodeURIComponent(taskId)}`);
    }

    saveManualDecision(taskId, ruleId, { finalStatus, reason, supplementalEvidence = [] }) {
      return this.request(`/api/tasks/${encodeURIComponent(taskId)}/rules/${encodeURIComponent(ruleId)}/manual-decision`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          final_status: finalStatus,
          reason,
          supplemental_evidence: supplementalEvidence
        })
      });
    }

    completeTask(taskId) {
      return this.request(`/api/tasks/${encodeURIComponent(taskId)}/complete`, { method: 'POST' });
    }

    reopenTask(taskId) {
      return this.request(`/api/tasks/${encodeURIComponent(taskId)}/reopen`, { method: 'POST' });
    }

    listTemplates() {
      return this.request('/api/templates');
    }

    uploadTemplate({ source, name, version, actor }) {
      if (!source) throw new TypeError('source is required');
      const form = new this.FormData();
      form.append('source', source);
      form.append('name', name);
      form.append('version', version);
      form.append('actor', actor);
      return this.request('/api/templates', { method: 'POST', body: form });
    }

    getTemplate(templateId) {
      return this.request(`/api/templates/${encodeURIComponent(templateId)}`);
    }

    updateTemplateRule(templateId, ruleId, changes) {
      return this.request(`/api/templates/${encodeURIComponent(templateId)}/rules/${encodeURIComponent(ruleId)}`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(changes)
      });
    }

    addTemplateRule(templateId, rule) {
      return this.request(`/api/templates/${encodeURIComponent(templateId)}/rules`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(rule)
      });
    }

    deleteTemplateRule(templateId, ruleId) {
      return this.request(`/api/templates/${encodeURIComponent(templateId)}/rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
    }

    publishTemplate(templateId) {
      return this.request(`/api/templates/${encodeURIComponent(templateId)}/publish`, { method: 'POST' });
    }

    retireTemplate(templateId) {
      return this.request(`/api/templates/${encodeURIComponent(templateId)}/retire`, { method: 'POST' });
    }
  }

  window.HardwareReviewApi = Object.freeze({ ApiClient, ApiError });
}());
