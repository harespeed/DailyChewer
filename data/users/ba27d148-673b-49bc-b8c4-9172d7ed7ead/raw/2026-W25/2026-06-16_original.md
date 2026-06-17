# 2026-06-16

这些内容来自用户当天写下的日报便条，请在不虚构具体事实的前提下生成结构化日报。

## 下午

完成的abra错别字服务的更新：兼容旧服务设计理念。在原有的字段基础上，添加了新字段，默认为text格式输入格式，改成html mode之后，输入应该为html-code，输出也是html-code，保留了原有的段落格式。

## 下午

数字员工本应该通过server manager1的9222去访问cdp，通过域名无法访问，通过ip可以访问，说明是安全组问题。改成了9226，可以访问，9226以前是browser node4的port，但是现在仍可以使用。由于browser node4已经暂时停用，所以让数字员工browser node6使用browser node4的cdp url

## 上午

继续构建m4mac上的数字员工，别的browser node使用的旧的逻辑是通过3个port（cdp url，noVNC url，file api）来访问对应的browser node，现在server manager1上的ws-relay只会listen 127.0.0.1，不会对外网开放，必须走https去访问。
因为原有的api服务是通过cdp url，noVNC，file api去操控remote browser node，但数据员工的原理是通过ws-relay来转发流量，cdp url的功能名存实亡。但又不能因为数字员工这个特例去修改api服务的代码(在api服务中体现在cdp_publishush.py中)，所以只能改动数字员工(m4macbook上的browser)的code，将欺骗api服务，让其以为拿到了cdp url，实际上cdp走的是ws-relay转发。
