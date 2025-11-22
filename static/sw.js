self.addEventListener('install', function(e){ self.skipWaiting();});
self.addEventListener('activate', function(e){ self.clients.claim();});
self.addEventListener('notificationclick', function(e){ e.notification.close(); });
