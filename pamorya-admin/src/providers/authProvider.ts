import type { AuthProvider } from "@refinedev/core";
import { apiClient } from "./dataProvider";

const STORAGE_KEY = "adminKey";

export const authProvider: AuthProvider = {
  login: async ({ password }) => {
    // Test the key against the backend before accepting
    const testKey = password as string;
    try {
      await apiClient.get("/admin/dashboard", {
        headers: { "x-admin-key": testKey },
      });
      localStorage.setItem(STORAGE_KEY, testKey);
      return { success: true, redirectTo: "/" };
    } catch {
      return {
        success: false,
        error: { name: "Login Failed", message: "Invalid admin key." },
      };
    }
  },

  logout: async () => {
    localStorage.removeItem(STORAGE_KEY);
    return { success: true, redirectTo: "/login" };
  },

  check: async () => {
    const key = localStorage.getItem(STORAGE_KEY);
    if (key) return { authenticated: true };
    return { authenticated: false, redirectTo: "/login" };
  },

  getIdentity: async () => {
    return { name: "Pamorya Admin", avatar: undefined };
  },

  onError: async (error) => {
    if (error?.response?.status === 401) {
      return { logout: true, redirectTo: "/login" };
    }
    return { error };
  },
};
