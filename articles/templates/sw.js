const CACHE_NAME = 'leblibrary-cache-v1';
const urlsToCache = [
  '/',
  // כאן נוסיף בהמשך נתיבים לקבצי CSS ו-JS מרכזיים כדי שיטענו מיידית
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // מחזיר מהמטמון אם יש, אחרת מושך מהרשת
        return response || fetch(event.request);
      })
  );
});