# Antex Analytics Portal

Antex uchun Superset boshqaruv portalining boshlang'ich versiyasi.

## Imkoniyatlar

- Antex logotipi bilan animatsiyali bosh sahifa
- Sessiya asosidagi admin autentifikatsiyasi
- Foydalanuvchilarni yaratish, tahrirlash, faollashtirish va o'chirish
- Admin, muharrir va kuzatuvchi rollari
- Superset REST API orqali datasetlarni sinxronlash, yaratish, tahrirlash va o'chirish
- Superset datasetlarini portal ichidagi papkalar va taglar bilan tartiblash
- Metabase querylarini collectionlar bo'yicha ko'rish va qidirish
- Metabase querylarini tahrirlash, nusxalash, ko'chirish va Trash bo'limiga o'tkazish
- Metabase collection daraxtida ishlash, yangi papka va SQL query yaratish

## Ishga tushirish

```bash
cp .env.example .env
docker compose up -d --build
```

`.env` faylida Superset uchun `SUPERSET_URL`, `SUPERSET_USERNAME`,
`SUPERSET_PASSWORD`, Metabase uchun esa `METABASE_URL`, `METABASE_USERNAME`,
`METABASE_PASSWORD` qiymatlari berilishi kerak.

Ilova standart holatda `127.0.0.1:8108` manziliga bog'lanadi.
