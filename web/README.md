# Douyin Downloader — Web UI

Front-end tĩnh + 2 Vercel serverless Python functions (`/api/extract`, `/api/proxy`).

## Cấu trúc

```
web/
├── index.html              # UI seekin-style
├── static/{style.css, app.js}
├── api/
│   ├── extract.py          # POST {urls: []} → scan metadata
│   └── proxy.py            # GET  ?url=&name= → stream file từ CDN
├── douyin_crawler/         # Vendored signature crawler (Evil0ctal)
├── requirements.txt        # requests, gmssl
└── vercel.json             # Build + route config
```

## Deploy lên Vercel

**1. Tạo repo private mới trên GitHub** (vd `ozvietnam/douyin-downloader`).

**2. Copy thư mục `web/` ra repo mới:**
```bash
git clone <your-new-private-repo> dy-web && cd dy-web
cp -r /path/to/vnhscode/web/. .
git add . && git commit -m "Initial web app" && git push
```

**3. Trên Vercel:**
- New Project → Import từ GitHub repo vừa tạo
- Framework Preset: **Other** (không chọn Next.js)
- Root Directory: để mặc định (repo root, vì vercel.json ở đó)
- Deploy

Vercel sẽ tự động re-deploy khi bạn push commit mới.

## Chạy local (dev)

```bash
cd web
pip install -r requirements.txt
# UI + proxy: dùng Vercel CLI
npx vercel dev
```

Hoặc test API Python trực tiếp:
```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from api.extract import extract_one
print(extract_one('https://v.douyin.com/ltVY25xQeBQ/'))
"
```

## Giới hạn đã biết

- **Vercel IP ở US/EU**: Douyin có thể trả empty response do geo-fence. Nếu `/api/extract` luôn báo "Fetch detail fail", chạy phần API ở server có IP VN/CN (VPS, Railway, Fly.io ở Asia).
- **50MB function size**: không có Playwright trong deploy (dùng bản self-hosted ở repo gốc `vnhscode` nếu cần fallback browser).
- **Timeout serverless**: mặc định 10s (Hobby) / 60s (Pro). `/api/proxy` cần 60s cho video lớn — đã set `maxDuration` trong `vercel.json`.
