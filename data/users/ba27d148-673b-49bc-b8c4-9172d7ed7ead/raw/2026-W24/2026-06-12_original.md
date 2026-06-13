# 2026-06-12

这些内容来自用户当天写下的日报便条，请在不虚构具体事实的前提下生成结构化日报。

## 下午

继续在server上做ws-relay，转发至nginx做本地数字员工

## 上午

继续修正browser node3 cdp url的9225 port的500问题，发现log中出现GetMimeType doesn't know mime错误，但这条ERROR只会在Chrome收到对/page/.../的普通HTTP GET请求才会出现，而不是WebSocket的请求，这说明，外部服务(XHS api，DY api)正在使用HTTP GET去请求websocket断电，不是请求WebSocket连接(handshake)，在$ curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==" \
     -H "Sec-WebSocket-Version: 13" \
     http://172.31.0.5:9225/devtools/page/CBA398817693B992A263AB636FCB8C0C
中返回为：HTTP/1.1 101 WebSocket Protocol Handshake
Upgrade: WebSocket
Connection: Upgrade
Sec-WebSocket-Accept: HSmrc0sMlYUkAGmm5OPpG2HaGWk=

^C

## 直接错因：
Nginx 代理配置中，监听 9225 端口的 server 块缺少 proxy_set_header Connection "upgrade" 这一指令。原本该行被注释或删除，导致 Nginx 在转发客户端请求时，没有将客户端的 Connection: Upgrade 头部传递给后端的 Chrome。由于缺少该必要头部，Chrome 无法识别这是一个 WebSocket 升级请求，于是将其当作普通 HTTP GET 请求处理，返回 HTTP 500 错误，并打印 GetMimeType doesn't know mime type for: page/... 警告。恢复该配置（重新添加 proxy_set_header Connection "upgrade"）并 reload Nginx 后，WebSocket 升级成功，500 错误消失。

## 根本错因：
外部客户端 A ──┐
                ├──▶ socat(fork,无限制) ──▶ Chrome :9222 ──▶ 竞争！
外部客户端 B ──┘         (TCP透传)              (同一WS端点)

Chrome DevTools Server 在处理同一浏览器级 WebSocket 端点的并发连接时存在竞争条件（race condition）。当多个client几乎同时使用同一个 /devtools/browser/<uuid> 发起连接请求时，Chrome 内部状态机可能出现异常，本应拒绝第二个连接（因为已有活跃连接），但由于并发竞争，导致后续请求被错误地作为普通 HTTP 请求处理，返回 500 而非规范的拒绝错误码503(server unavailable)。该缺陷在低并发时不易触发，但一旦存在瞬时并发（如多个外部服务同时重连、Nginx 同时转发多个请求），就可能导致部分连接失败。原本 Nginx 配置正确，问题仍会出现，是因为并发竞争触发了 Chrome 内部的这个Bug。而恢复 Nginx 配置后问题消失，是因为 Nginx reload 改变了请求时序，避开了竞争条件。但是如果不修改BrowserNode，该问题仍会出现。

## 外部服务访问BrowserNode的原理：
CDP Client 向 Chrome 的远程调试端口（例如 http://<host>:9225/json/version）发送 GET 请求，获取返回的 JSON 中的 webSocketDebuggerUrl，其值出现诸如ws://<host>:9225/devtools/browser/<uuid>。
客户端使用该 URL 发起 HTTP 升级请求，请求头中必须包含：
Connection: Upgrade
Upgrade: websocket
其他 WebSocket 专用头部（Sec-WebSocket-Key、Sec-WebSocket-Version）。Chrome 若同意升级，则返回 101 Switching Protocols，此后客户端即可通过该 WebSocket 发送 JSON-RPC 命令（如 Browser.getVersion、Target.createTarget、Page.navigate 等），Chrome 执行后返回响应。Chrome 对每个浏览器级 WebSocket 端点（/devtools/browser/<uuid>）只允许一个活跃连接；新连接请求会被拒绝。

##解决方案
在代理层做"WebSocket 排队锁"
在 socat 的位置塞一个 7 层代理（cdp_ws_lock_proxy.py），它知道 HTTP / WebSocket 协议语义，可以做并发控制。核心设计：按 path 维度的纯排队锁（asyncio.Lock）
客户端 A ─┐
客户端 B ─┼─→ [代理]  ─同一 /devtools/browser/xxx──→ Chrome (永远只让 1 个进入)
客户端 C ─┘
所以MinerFactory.Runner会需要做一下修改，这大概率会导致request的执行速度变缓，但会增加MinerFactory整体的稳定性。
