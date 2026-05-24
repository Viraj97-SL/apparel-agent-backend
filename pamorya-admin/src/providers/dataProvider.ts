import type { DataProvider } from "@refinedev/core";
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const apiClient = axios.create({ baseURL: API_URL });

// Attach admin key to every request
apiClient.interceptors.request.use((config) => {
  const key = localStorage.getItem("adminKey") ?? import.meta.env.VITE_ADMIN_KEY;
  if (key) config.headers["x-admin-key"] = key;
  return config;
});

export const dataProvider: DataProvider = {
  getList: async ({ resource, pagination, filters }) => {
    const { current = 1, pageSize = 20 } = pagination ?? {};
    const params: Record<string, string | number> = { page: current, pageSize };

    // Map Refine filters to query params our API understands
    if (filters) {
      for (const f of filters) {
        if ("field" in f && f.operator === "contains" && f.value) {
          params[f.field] = f.value;
        }
        if ("field" in f && f.operator === "eq" && f.value && f.value !== "All") {
          params[f.field] = f.value;
        }
      }
    }

    const { data } = await apiClient.get(`/admin/${resource}`, { params });
    return { data: data.data, total: data.total };
  },

  getOne: async ({ resource, id }) => {
    const { data } = await apiClient.get(`/admin/${resource}/${id}`);
    return { data };
  },

  create: async ({ resource, variables }) => {
    const { data } = await apiClient.post(`/admin/${resource}`, variables);
    return { data };
  },

  update: async ({ resource, id, variables }) => {
    const { data } = await apiClient.patch(`/admin/${resource}/${id}`, variables);
    return { data };
  },

  deleteOne: async ({ resource, id }) => {
    const { data } = await apiClient.delete(`/admin/${resource}/${id}`);
    return { data };
  },

  getApiUrl: () => API_URL,

  // Not used — kept to satisfy the interface
  getMany: async ({ resource, ids }) => {
    const results = await Promise.all(
      ids.map((id) => apiClient.get(`/admin/${resource}/${id}`))
    );
    return { data: results.map((r) => r.data) };
  },
};
