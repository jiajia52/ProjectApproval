export async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || text || "请求失败。");
  }
  return payload;
}

export function projectDisplayValue(project, ...keys) {
  for (const key of keys) {
    const value = project?.[key];
    if (value !== null && value !== undefined && String(value).trim() !== "") {
      return String(value);
    }
  }
  return "";
}

export function buildUiUrl(pathname, query = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, String(value));
    }
  });
  const queryString = params.toString();
  return `/ui${pathname}${queryString ? `?${queryString}` : ""}`;
}
