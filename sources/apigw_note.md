# 官方赛题数据接口记录（可复核）

本目录下的 `comp_raw.json` 与 `赛题原文_zone98269700.md` 通过华为 ICT 大赛官网自身调用的公开接口获得，任何人都可复现。

## 接口

```
GET https://apigw-ae.huawei.com/api/services/lras/cams/v1/comps/queryHtmlContext
      ?zoneId=98269700
      &jalorVersion=e20250901
      &X-HW-ID=com.huawei.prm.talent
      &env=
      &language=zh_CN
      &x-tenantId=com.huawei.prm.talent.talent_ubms_msaId
```

请求头：

```
Accept: application/json
Origin: https://e.huawei.com
Referer: https://e.huawei.com/cn/talent/
```

备用网关（同一份数据，任选其一可用）：`apigw-ae.huawei.com` / `apigw-04.huawei.com` / `apigw-01.huawei.com`

## 参数说明

| 参数 | 值 | 来源 |
| --- | --- | --- |
| zoneId | 98269700 | 报名链接中的 `zoneId` |
| zoneCode | 027425 | 报名链接中的 `zoneCode`（中国区） |
| compId | 85132021 | 报名链接中的 `compId`（2026-2027 创新赛） |
| jalorVersion | 任意值 | 前端用于绕缓存，实测可随意传 |

## 其他可用接口

- 赛事列表：`GET /api/services/lras/cams/v1/ruuningComp?compCategory=innovation&currentPage=1&pageSize=500`
- 团队/报名状态：`GET /api/services/lras/cams/iCompQueryService/v2/findRegZoneInfo?zoneId=..&compId=..&compCategory=innovation`（**需登录**，未登录返回 `{"status":403,"message":"the user has not logged in"}`）

## 为什么用这种方式

本机环境无法直连网页（`web_fetch` 判定域名为非公网地址；Windows Schannel 在本机取不到 TLS 凭证，`curl` 报 `SEC_E_NO_CREDENTIALS`），只有 Python 的 TLS 栈可用。因此通过 Python 复现官网前端自身的接口调用来获取权威原文。

复现命令（Python 3）：

```python
import ssl, urllib.request, json
ctx = ssl.create_default_context()
url = ("https://apigw-ae.huawei.com/api/services/lras/cams/v1/comps/queryHtmlContext"
       "?zoneId=98269700&jalorVersion=e20250901"
       "&X-HW-ID=com.huawei.prm.talent&env=&language=zh_CN"
       "&x-tenantId=com.huawei.prm.talent.talent_ubms_msaId")
req = urllib.request.Request(url, headers={"Accept": "application/json",
      "Origin": "https://e.huawei.com", "Referer": "https://e.huawei.com/cn/talent/"})
print(json.dumps(json.loads(urllib.request.urlopen(req, timeout=30, context=ctx).read()), ensure_ascii=False)[:2000])
```

## 已知边界

- 该接口只返回**公开的赛题与规则文本**，不含个人报名信息与团队数据。
- 数据会随官方更新变化（当前 `numberVersion=88`，官方最后更新 2026-10-08），重要决策前请重新拉取一次。
