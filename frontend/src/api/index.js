import axios from 'axios'
import { message } from 'ant-design-vue'

const http = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const detail = err.response?.data?.detail
    const text = Array.isArray(detail)
      ? detail.map((d) => d.msg || d).join('; ')
      : detail || err.message || '请求失败'
    message.error(text)
    return Promise.reject(err)
  },
)

export const api = {
  health: () => http.get('/health'),
  listTasks: () => http.get('/tasks'),
  listDatasources: () => http.get('/tasks/datasources'),
  createTask: (data) => http.post('/tasks', data),
  createDemo: () => http.post('/tasks/demo'),
  getTask: (id, params) => http.get(`/tasks/${id}`, { params }),
  updateTask: (id, data) => http.put(`/tasks/${id}`, data),
  downloadReportPdf: (id) =>
    http.get(`/tasks/${id}/export-pdf`, { responseType: 'blob', timeout: 120000 }),
  copyTask: (id) => http.post('/tasks/copy', { task_id: id }),
  deleteTask: (id) => http.delete(`/tasks/${id}`),
  testConnection: (config) => http.post('/tasks/test-connection', { config }),
  databases: (taskId, side) => http.get(`/compare/${taskId}/databases`, { params: { side } }),
  schemas: (taskId, side, database) =>
    http.get(`/compare/${taskId}/schemas`, { params: { side, database } }),
  tables: (taskId, side, database, schema_name) =>
    http.get(`/compare/${taskId}/tables`, { params: { side, database, schema_name } }),
  columns: (taskId, side, database, table, schema_name) =>
    http.get(`/compare/${taskId}/columns`, { params: { side, database, table, schema_name } }),
  rows: (taskId, side, database, table, schema_name, limit = 1000, offset = 0) =>
    http.get(`/compare/${taskId}/rows`, {
      params: { side, database, table, schema_name, limit, offset },
    }),
  rowCount: (taskId, side, database, table, schema_name) =>
    http.get(`/compare/${taskId}/row-count`, {
      params: { side, database, table, schema_name },
    }),
  values: (taskId, side, database, table, column, schema_name) =>
    http.get(`/compare/${taskId}/values`, {
      params: { side, database, table, column, schema_name },
    }),
  rowMatch: (taskId, data) =>
    http.post(`/compare/${taskId}/row-match`, data, { timeout: 300000 }),
  rowMatchOverlay: (taskId, data) =>
    http.post(`/compare/${taskId}/row-match-overlay`, data),
  unmatchedRows: (taskId, data) =>
    http.post(`/compare/${taskId}/unmatched-rows`, data, { timeout: 300000 }),
  searchRows: (taskId, data) =>
    http.post(`/compare/${taskId}/search-rows`, data, { timeout: 300000 }),
  rowMatchEdit: (taskId, data) =>
    http.post(`/compare/${taskId}/row-match-edit`, data),
  rowsByIndices: (taskId, data) =>
    http.post(`/compare/${taskId}/rows-by-indices`, data, { timeout: 300000 }),
  rowsByValues: (taskId, data) =>
    http.post(`/compare/${taskId}/rows-by-values`, data, { timeout: 300000 }),
  exportRows: (taskId, data) =>
    http.post(`/compare/${taskId}/export-rows`, data, {
      responseType: 'blob',
      timeout: 600000,
    }),
}

export default api
