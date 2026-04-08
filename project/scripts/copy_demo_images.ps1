# Копирует демо-фото товаров из папки Cursor assets в static/products (если assets есть).
$dst = Join-Path $PSScriptRoot "..\static\products"
$src = Join-Path $env:USERPROFILE ".cursor\projects\c-Users-User-Documents-GitHub-SpiralHub-AI\assets"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
if (-not (Test-Path $src)) {
    Write-Host "Папка assets не найдена: $src"
    exit 1
}
$map = @{
  "820bb71d-6029-4376-b1b5-5a505783f840" = "wood_figurines.png"
  "917f44a4-466a-4733-85bb-b072d50482b8" = "cucumbers.png"
  "0084f180-71ad-4691-b42f-dc5b73293490" = "terracotta_mini_vase.png"
  "afdcdd65-435d-4121-9e17-ecd615e310bf" = "ceramic_rippled_vase.png"
  "24d7e4c5-8efe-4a7b-9714-154ce9f56e91" = "white_embossed_vase.png"
  "5d1c6502-e4dc-477e-805a-dfc160469c20" = "eggplants.png"
  "5989d46c-1336-4c34-9d1a-1e01aef33672" = "pompom_rug.png"
  "1da45e4e-63cf-46cb-b219-5aa35aaefee7" = "rag_rug_stripes.png"
  "99c6028f-8bfe-4f87-b326-b3006d4e6290" = "mini_amphora.png"
  "0e2bd16d-7607-46f1-abe0-9cc2e18cfb92" = "wicker_basket.png"
  "3f66572d-e999-4547-98ee-e47a458f7553" = "bulk_grain.png"
  "7b7c0a9f-87c7-49e3-82b7-4dbae98f6542" = "dragon_fruit_plants.png"
  "c71af623-c376-456f-b3db-04821da14189" = "terracotta_vase_etched.png"
  "465d2e01-8c4b-4948-8eb2-4d418a5b630f" = "studio_pottery.png"
}
foreach ($k in $map.Keys) {
  $f = Get-ChildItem $src -Filter "*$k*" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($f) { Copy-Item $f.FullName (Join-Path $dst $map[$k]) -Force }
}
Write-Host "Готово:" (Get-ChildItem $dst -File).Count "файлов в $dst"
