// YeparDTE — src/utils/generarPDF.js
// Genera PDF en formato Carta/A4 o Ticket 80mm (impresora térmica)
// Usa solo APIs nativas del browser — sin dependencias externas

const BASE = import.meta.env.VITE_API_URL || 'https://yepardte-backend-production.up.railway.app'

// ── Obtener logo y ancho desde el backend ─────────────────────────────────────
// Analogía: el membrete de la empresa guardado en la caja fuerte —
// solo se busca cuando se necesita imprimir, no antes.
async function obtenerLogoEmpresa(token) {
  if (!token) return { logo_base64: null, logo_ancho: 70 }
  try {
    const res = await fetch(`${BASE}/api/empresa/logo`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!res.ok) return { logo_base64: null, logo_ancho: 70 }
    return await res.json()
  } catch {
    return { logo_base64: null, logo_ancho: 70 }
  }
}

// ── Selector de formato ───────────────────────────────────────────────────────
function elegirFormato() {
  return new Promise((resolve) => {
    const overlay = document.createElement('div')
    overlay.style.cssText = `
      position:fixed; inset:0; background:rgba(0,0,0,0.55);
      display:flex; align-items:center; justify-content:center;
      z-index:99999; font-family:Arial,sans-serif;
    `
    overlay.innerHTML = `
      <div style="background:#fff; border-radius:14px; padding:28px 32px; min-width:320px; box-shadow:0 8px 40px rgba(0,0,0,0.25);">
        <div style="font-size:15px; font-weight:700; margin-bottom:4px; color:#111;">Formato de impresión</div>
        <div style="font-size:12px; color:#888; margin-bottom:20px;">¿En qué tipo de papel vas a imprimir?</div>
        <div style="display:flex; gap:12px;">
          <button id="fmt-carta" style="
            flex:1; padding:16px 10px; border:2px solid #e2e8f0; border-radius:10px;
            background:#fff; cursor:pointer; font-size:13px; font-weight:600; color:#111;
            display:flex; flex-direction:column; align-items:center; gap:6px;">
            <span style="font-size:26px;">📄</span>
            <span>Carta / A4</span>
            <span style="font-size:10px; color:#999; font-weight:400;">Hoja estándar 210mm</span>
          </button>
          <button id="fmt-ticket" style="
            flex:1; padding:16px 10px; border:2px solid #e2e8f0; border-radius:10px;
            background:#fff; cursor:pointer; font-size:13px; font-weight:600; color:#111;
            display:flex; flex-direction:column; align-items:center; gap:6px;">
            <span style="font-size:26px;">🧾</span>
            <span>Ticket 80mm</span>
            <span style="font-size:10px; color:#999; font-weight:400;">Impresora térmica</span>
          </button>
        </div>
        <button id="fmt-cancel" style="
          width:100%; margin-top:14px; padding:8px; border:none; background:none;
          color:#aaa; font-size:12px; cursor:pointer; border-radius:6px;">Cancelar</button>
      </div>
    `
    document.body.appendChild(overlay)
    const cleanup = (fmt) => { document.body.removeChild(overlay); resolve(fmt) }
    document.getElementById('fmt-carta').onclick  = () => cleanup('carta')
    document.getElementById('fmt-ticket').onclick = () => cleanup('ticket')
    document.getElementById('fmt-cancel').onclick = () => cleanup(null)
    overlay.onclick = (e) => { if (e.target === overlay) cleanup(null) }
  })
}

// ── Generador principal ───────────────────────────────────────────────────────
export async function generarPDFDocumento(doc, empresa, token = null) {
  const formato = await elegirFormato()
  if (!formato) return

  // Obtener logo del backend (con token para autenticarse)
  const { logo_base64: logoBase64, logo_ancho: logoAncho } = await obtenerLogoEmpresa(token)

  const esExenta = doc.tipoCode === '41' || doc.tipo === 'Boleta Exenta' || doc.exento === true
  const esBoleta = doc.tipoCode === '39' || doc.tipoCode === '41' || doc.tipo === 'Boleta' || doc.tipo === 'Boleta Exenta'

  const esFacturaExenta = (doc.tipoCode === '33' || doc.tipo === 'Factura' || doc.tipo === 'Factura Exenta') && (doc.exento === true || doc.tipo === 'Factura Exenta')
  const tipoLabel = esExenta
    ? 'BOLETA EXENTA ELECTRÓNICA'
    : esBoleta
      ? 'BOLETA ELECTRÓNICA'
      : esFacturaExenta
        ? 'FACTURA EXENTA ELECTRÓNICA'
        : 'FACTURA ELECTRÓNICA'

  const colorDoc = esBoleta ? '#1a56db' : '#c00'

  const total      = doc.monto ?? doc.total ?? 0
  const netoExento = doc.netoExento ?? (esExenta ? total : 0)
  const neto       = doc.neto ?? (esExenta ? 0 : (esBoleta ? total : Math.round(total / 1.19)))
  const iva        = doc.iva  ?? (esExenta ? 0 : (esBoleta ? 0 : total - Math.round(total / 1.19)))
  const items      = doc.items ?? [{ descripcion: doc.receptor, cant: 1, precioUnit: total, descuento: 0, valor: total }]

  const ctx = { doc, empresa, tipoLabel, colorDoc, esExenta, esBoleta, total, neto, netoExento, iva, items, logoBase64, logoAncho: logoAncho || 70 }
  const html = formato === 'ticket' ? htmlTicket(ctx) : htmlCarta(ctx)

  const winW = formato === 'ticket' ? 380 : 900
  const win  = window.open('', '_blank', `width=${winW},height=700`)
  win.document.write(html)
  win.document.close()
  win.onload = () => { win.focus(); win.print() }
}

// ── Bloque de totales compartido ─────────────────────────────────────────────
function bloquesTotalesCarta(esExenta, neto, netoExento, iva, total) {
  return `
    ${esExenta ? `
    <div class="total-row"><span class="total-label">MONTO NETO $</span><span>$0</span></div>
    <div class="total-row"><span class="total-label">MONTO EXENTO $</span><span>$${netoExento.toLocaleString('es-CL')}</span></div>
    <div class="total-row"><span class="total-label">I.V.A. 19% $</span><span class="exento-badge">EXENTO</span></div>
    ` : `
    <div class="total-row"><span class="total-label">MONTO NETO $</span><span>$${neto.toLocaleString('es-CL')}</span></div>
    <div class="total-row"><span class="total-label">I.V.A. 19% $</span><span>$${iva.toLocaleString('es-CL')}</span></div>
    `}
    <div class="total-row final"><span class="total-label">TOTAL $</span><span>$${total.toLocaleString('es-CL')}</span></div>
  `
}

// ── HTML CARTA ────────────────────────────────────────────────────────────────
function htmlCarta({ doc, empresa, tipoLabel, colorDoc, esExenta, total, neto, netoExento, iva, items, logoBase64, logoAncho }) {
  // Si hay logo → mostrarlo en el header izquierdo
  // Si no hay logo → mostrar texto (RUT, tipo, N°) como antes
  const headerIzquierdo = logoBase64 ? `
    <div class="header-logo-wrap">
      <img src="${logoBase64}" class="empresa-logo" alt="Logo empresa"
           style="width:${logoAncho}px; height:auto; max-height:90px; object-fit:contain;" />
      <div style="margin-top:6px;">
        <div class="emisor-nombre">${empresa.razonSocial ?? empresa.nombre}</div>
        <div class="emisor-datos">
          Giro: ${empresa.giro}<br/>
          ${empresa.direccion} - ${(empresa.comuna ?? '').toUpperCase()} - ${(empresa.ciudad ?? '').toUpperCase()}<br/>
          ${empresa.telefono ? `Tel: ${empresa.telefono}` : ''}
        </div>
      </div>
    </div>
  ` : `
    <div class="emisor-rut">R.U.T. ${empresa.rut}</div>
    <div class="emisor-tipo">${tipoLabel}</div>
    <div class="emisor-num">N° ${String(doc.folio ?? doc.numero).padStart(11, '0')}</div>
    <div class="sii-logo">S.I.I. — ${empresa.ciudad ?? 'SANTIAGO'}</div><br/>
    <div class="emisor-nombre">${empresa.razonSocial ?? empresa.nombre}</div>
    <div class="emisor-datos">
      Giro: ${empresa.giro}<br/>
      ${empresa.direccion} - ${(empresa.comuna ?? '').toUpperCase()} - ${(empresa.ciudad ?? '').toUpperCase()}<br/>
      ${empresa.telefono ? `Tel: ${empresa.telefono}` : ''}
    </div>
  `

  return `<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>${tipoLabel} N° ${doc.numero}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#000;background:#fff}
  .page{width:210mm;min-height:297mm;padding:12mm;position:relative}
  .header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;border-bottom:2px solid #000;padding-bottom:8px}
  .header-left{flex:1}
  .header-logo-wrap{display:flex;flex-direction:column;align-items:flex-start;gap:4px}
  .empresa-logo{display:block}
  .emisor-rut{font-size:14px;font-weight:bold;margin-bottom:2px}
  .emisor-tipo{font-size:18px;font-weight:bold;margin-bottom:2px}
  .emisor-num{font-size:13px;font-weight:bold;color:#333;margin-bottom:4px}
  .sii-logo{font-size:10px;color:#555;margin-bottom:4px}
  .emisor-nombre{font-size:13px;font-weight:bold;margin-bottom:2px}
  .emisor-datos{font-size:10px;color:#333;line-height:1.5}
  /* Cuadro DTE derecha — ahora incluye RUT de la empresa */
  .doc-box{border:2px solid ${colorDoc};border-radius:4px;padding:8px 14px;text-align:center;min-width:160px}
  .doc-box-rut{font-size:11px;font-weight:bold;color:${colorDoc};margin-bottom:4px;letter-spacing:0.3px}
  .doc-box-tipo{font-size:12px;font-weight:bold;color:${colorDoc};margin-bottom:4px}
  .doc-box-num{font-size:22px;font-weight:bold;color:${colorDoc}}
  .receptor-section{background:#f5f5f5;border:1px solid #ddd;border-radius:3px;padding:8px 10px;margin-bottom:10px}
  .receptor-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px 16px}
  .r-field{display:flex;gap:4px;align-items:baseline}
  .r-label{font-size:9px;font-weight:bold;text-transform:uppercase;color:#666;white-space:nowrap}
  .r-val{font-size:11px;font-weight:600;border-bottom:1px solid #ccc;flex:1;min-width:0;word-break:break-all}
  .r-full{grid-column:1/-1}
  .items-table{width:100%;border-collapse:collapse;margin-bottom:10px}
  .items-table th{background:#333;color:#fff;font-size:9px;font-weight:bold;text-transform:uppercase;padding:5px 6px;text-align:left}
  .items-table th.right{text-align:right}
  .items-table td{padding:5px 6px;font-size:10px;border-bottom:1px solid #eee}
  .items-table td.right{text-align:right}
  .items-table tr:nth-child(even) td{background:#fafafa}
  .items-table .num{width:30px;text-align:center}
  .totales-wrap{display:flex;justify-content:flex-end;margin-bottom:12px}
  .totales-box{width:220px}
  .total-row{display:flex;justify-content:space-between;padding:3px 0;font-size:11px;border-bottom:1px solid #eee}
  .total-row.final{font-size:13px;font-weight:bold;border-bottom:2px solid #000;padding:5px 0}
  .total-label{color:#333}
  .exento-badge{font-size:9px;font-weight:bold;color:#1a56db;background:#e8f0fe;border:1px solid #a8c0f8;border-radius:4px;padding:1px 6px}
  .timbre-section{border-top:2px solid #000;padding-top:8px;display:flex;justify-content:space-between;align-items:flex-start}
  .timbre-left{flex:1}
  .timbre-title{font-size:9px;font-weight:bold;text-transform:uppercase;margin-bottom:4px}
  .timbre-sii{font-size:9px;color:#555}
  .timbre-right{text-align:right;font-size:9px}
  .sin-cert{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%) rotate(-30deg);font-size:28px;font-weight:bold;color:rgba(200,0,0,0.08);text-align:center;pointer-events:none;white-space:nowrap;z-index:0}
  .no-cert-badge{background:#fff3cd;border:1px solid #ffc107;border-radius:3px;padding:4px 8px;font-size:9px;font-weight:bold;color:#856404;text-align:center;margin-bottom:8px}
  .footer{margin-top:20px;border-top:1px solid #ccc;padding-top:6px;font-size:8px;color:#999;text-align:center}
  @media print{.page{padding:8mm}body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body>
<div class="page">
  ${!doc.certificado ? `<div class="sin-cert">DOCUMENTO INTERNO · SIN VALIDEZ FISCAL · PENDIENTE CERTIFICACIÓN DTE</div>` : ''}
  ${!doc.certificado ? `<div class="no-cert-badge">⚠ DOCUMENTO INTERNO — SIN VALIDEZ FISCAL — PENDIENTE CERTIFICACIÓN DTE</div>` : ''}
  <div class="header">
    <div class="header-left">
      ${headerIzquierdo}
    </div>
    <!-- Cuadro DTE derecha: RUT empresa + tipo + N° -->
    <div class="doc-box">
      <div class="doc-box-rut">R.U.T. ${empresa.rut}</div>
      <div class="doc-box-tipo">${tipoLabel}</div>
      <div class="doc-box-num">N° ${String(doc.folio ?? 0).padStart(11, '0')}</div>
    </div>
  </div>
  <div class="receptor-section">
    <div class="receptor-grid">
      <div class="r-field r-full"><span class="r-label">SEÑOR(ES):</span><span class="r-val">${doc.receptor ?? doc.receptorNombre ?? ''}</span></div>
      <div class="r-field"><span class="r-label">R.U.T.:</span><span class="r-val">${doc.rut ?? doc.receptorRut ?? ''}</span></div>
      <div class="r-field"><span class="r-label">GIRO:</span><span class="r-val">${doc.receptorGiro ?? ''}</span></div>
      <div class="r-field r-full"><span class="r-label">DIRECCIÓN:</span><span class="r-val">${doc.receptorDireccion ?? ''}</span></div>
      <div class="r-field"><span class="r-label">FECHA EMISIÓN:</span><span class="r-val">${new Date(doc.fecha).toLocaleDateString('es-CL')}</span></div>
      <div class="r-field"><span class="r-label">CONDICIÓN PAGO:</span><span class="r-val">${doc.condicionPago ?? 'Contado'}</span></div>
    </div>
  </div>
  <table class="items-table">
    <thead><tr>
      <th class="num">N°</th><th>Codigo</th><th>Descripcion</th>
      <th class="right">Cant.</th><th class="right">Precio Unit.</th>
      <th class="right">%Desc.</th><th class="right">Valor</th>
    </tr></thead>
    <tbody>${items.map((item, i) => `
      <tr>
        <td class="num">${i + 1}</td>
        <td>${item.codigo ?? ''}</td>
        <td>${item.descripcion ?? item.nombre ?? item.desc ?? ''}</td>
        <td class="right">${item.cant ?? item.qty ?? 1}</td>
        <td class="right">$${Number(item.precioUnit ?? item.precio ?? 0).toLocaleString('es-CL')}</td>
        <td class="right">${item.descuento ?? 0}%</td>
        <td class="right">$${Number(item.valor ?? ((item.cant ?? item.qty ?? 1) * (item.precioUnit ?? item.precio ?? 0))).toLocaleString('es-CL')}</td>
      </tr>`).join('')}
    </tbody>
  </table>
  <div class="totales-wrap"><div class="totales-box">
    ${bloquesTotalesCarta(esExenta, neto, netoExento, iva, total)}
  </div></div>
  <div class="timbre-section">
    <div class="timbre-left">
      <div class="timbre-title">Timbre Electrónico SII</div>
      <div class="timbre-sii">Verifique documento en: www.sii.cl</div>
    </div>
    <div class="timbre-right">
      ${tipoLabel}<br/>N° ${String(doc.folio ?? 0).padStart(11, '0')}<br/>
      Emisión: ${new Date(doc.fecha).toLocaleDateString('es-CL')}<br/>RUT: ${empresa.rut}
    </div>
  </div>
  <div class="footer">Generado con YeparDTE · by YeparSolutions · yepardte.yeparsolutions.com</div>
</div></body></html>`
}

// ── HTML TICKET 80mm ──────────────────────────────────────────────────────────
function htmlTicket({ doc, empresa, tipoLabel, colorDoc, esExenta, total, neto, netoExento, iva, items, logoBase64, logoAncho }) {
  return `<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>${tipoLabel} N° ${doc.numero}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:Arial,Helvetica,sans-serif;font-size:10px;color:#000;background:#fff}
  .ticket{width:72mm;padding:4mm 3mm;margin:0 auto}
  .t-center{text-align:center}
  .t-logo{max-height:20mm;object-fit:contain;margin:0 auto 4px;display:block}
  .t-empresa{font-size:12px;font-weight:bold;margin-bottom:2px}
  .t-rut{font-size:9px;color:#333;margin-bottom:1px}
  .t-giro{font-size:9px;color:#555;margin-bottom:1px}
  .t-dir{font-size:8px;color:#666;margin-bottom:6px}
  .t-tipo-box{border:1.5px solid ${colorDoc};border-radius:4px;padding:5px 8px;text-align:center;margin:6px 0}
  .t-tipo-label{font-size:10px;font-weight:bold;color:${colorDoc}}
  .t-tipo-num{font-size:14px;font-weight:bold;color:${colorDoc};margin-top:2px}
  .t-divider{border:none;border-top:1px dashed #999;margin:5px 0}
  .t-divider-solid{border:none;border-top:1px solid #000;margin:5px 0}
  .t-receptor{font-size:9px;margin-bottom:4px}
  .t-receptor-row{display:flex;justify-content:space-between;padding:1px 0}
  .t-rlabel{color:#666;font-weight:600}
  .t-rval{text-align:right;max-width:55%;word-break:break-all}
  .t-items{width:100%;margin-bottom:4px;border-collapse:collapse}
  .t-items th{font-size:8px;font-weight:bold;text-transform:uppercase;padding:2px;border-bottom:1px solid #000}
  .t-items td{font-size:9px;padding:2px;border-bottom:1px dotted #ccc;vertical-align:top}
  .t-items .desc{max-width:30mm;word-break:break-word}
  .t-items .right{text-align:right}
  .t-totales{margin:4px 0}
  .t-total-row{display:flex;justify-content:space-between;padding:2px 0;font-size:9px}
  .t-total-final{font-size:13px;font-weight:bold;border-top:2px solid #000;padding-top:4px;margin-top:2px}
  .exento-badge{font-size:8px;font-weight:bold;color:#1a56db;background:#e8f0fe;border:1px solid #a8c0f8;border-radius:3px;padding:1px 4px}
  .t-timbre{font-size:8px;text-align:center;color:#555;margin-top:6px}
  .t-timbre strong{display:block;color:#000;margin-bottom:2px}
  .t-no-cert{background:#fff3cd;border:1px solid #ffc107;border-radius:3px;padding:3px 6px;font-size:8px;font-weight:bold;color:#856404;text-align:center;margin-bottom:6px}
  .t-footer{font-size:7px;color:#aaa;text-align:center;margin-top:8px}
  @media print{@page{margin:0;size:80mm auto}body{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body>
<div class="ticket">
  ${!doc.certificado ? `<div class="t-no-cert">⚠ SIN VALIDEZ FISCAL — DEMO</div>` : ''}
  <div class="t-center">
    ${logoBase64
      ? `<img src="${logoBase64}" class="t-logo" style="width:${Math.min(logoAncho, 50)}mm" alt="Logo" />`
      : ''
    }
    <div class="t-empresa">${empresa.razonSocial ?? empresa.nombre}</div>
    <div class="t-rut">RUT: ${empresa.rut}</div>
    <div class="t-giro">${empresa.giro}</div>
    <div class="t-dir">${empresa.direccion} · ${empresa.comuna ?? ''} · ${empresa.ciudad ?? ''}</div>
  </div>
  <div class="t-tipo-box">
    <div class="t-tipo-label">${tipoLabel}</div>
    <div class="t-tipo-num">N° ${String(doc.folio ?? doc.numero).padStart(8, '0')}</div>
  </div>
  <hr class="t-divider"/>
  <div class="t-receptor">
    <div class="t-receptor-row">
      <span class="t-rlabel">Cliente:</span>
      <span class="t-rval">${doc.receptor ?? doc.receptorNombre ?? 'Consumidor Final'}</span>
    </div>
    ${(doc.rut ?? doc.receptorRut) ? `
    <div class="t-receptor-row">
      <span class="t-rlabel">RUT:</span>
      <span class="t-rval">${doc.rut ?? doc.receptorRut}</span>
    </div>` : ''}
    <div class="t-receptor-row">
      <span class="t-rlabel">Fecha:</span>
      <span class="t-rval">${new Date(doc.fecha).toLocaleDateString('es-CL')}</span>
    </div>
    <div class="t-receptor-row">
      <span class="t-rlabel">Pago:</span>
      <span class="t-rval">${doc.condicionPago ?? 'Contado'}</span>
    </div>
  </div>
  <hr class="t-divider"/>
  <table class="t-items">
    <thead><tr>
      <th class="desc">Descripción</th>
      <th class="right">Qty</th>
      <th class="right">P.Unit</th>
      <th class="right">Total</th>
    </tr></thead>
    <tbody>${items.map(item => `
      <tr>
        <td class="desc">${item.descripcion ?? item.nombre ?? item.desc ?? ''}</td>
        <td class="right">${item.cant ?? item.qty ?? 1}</td>
        <td class="right">$${Number(item.precioUnit ?? item.precio ?? 0).toLocaleString('es-CL')}</td>
        <td class="right">$${Number(item.valor ?? ((item.cant ?? item.qty ?? 1) * (item.precioUnit ?? item.precio ?? 0))).toLocaleString('es-CL')}</td>
      </tr>`).join('')}
    </tbody>
  </table>
  <hr class="t-divider-solid"/>
  <div class="t-totales">
    ${esExenta ? `
    <div class="t-total-row"><span>Monto Neto</span><span>$0</span></div>
    <div class="t-total-row"><span>Monto Exento</span><span>$${netoExento.toLocaleString('es-CL')}</span></div>
    <div class="t-total-row"><span>I.V.A. 19%</span><span class="exento-badge">EXENTO</span></div>
    ` : `
    <div class="t-total-row"><span>Monto Neto</span><span>$${neto.toLocaleString('es-CL')}</span></div>
    <div class="t-total-row"><span>I.V.A. 19%</span><span>$${iva.toLocaleString('es-CL')}</span></div>
    `}
    <div class="t-total-row t-total-final">
      <span>TOTAL</span>
      <span>$${total.toLocaleString('es-CL')}</span>
    </div>
  </div>
  <hr class="t-divider"/>
  <div class="t-timbre">
    <strong>Timbre Electrónico SII</strong>
    Verifique en: www.sii.cl<br/>
    ${tipoLabel} · N° ${String(doc.folio ?? 0).padStart(8, '0')}<br/>
    Emisión: ${new Date(doc.fecha).toLocaleDateString('es-CL')} · RUT: ${empresa.rut}
  </div>
  <div class="t-footer">Generado con YeparDTE · yeparsolutions.com</div>
</div></body></html>`
}

// ── Genera HTML carta para adjuntar en email (sin abrir ventana) ──────────────
export async function generarHTMLParaEmail(doc, empresa, token = null) {
  const { logo_base64: logoBase64, logo_ancho: logoAncho } = await obtenerLogoEmpresa(token)

  const esExenta = doc.tipoCode === '41' || doc.tipo === 'Boleta Exenta' || doc.exento === true
  const esBoleta = doc.tipoCode === '39' || doc.tipoCode === '41' || doc.tipo === 'Boleta' || doc.tipo === 'Boleta Exenta'
  const tipoLabel = esExenta ? 'BOLETA EXENTA ELECTRÓNICA' : esBoleta ? 'BOLETA ELECTRÓNICA' : 'FACTURA ELECTRÓNICA'
  const colorDoc  = esBoleta ? '#1a56db' : '#c00'
  const total      = doc.monto ?? doc.total ?? 0
  const netoExento = doc.netoExento ?? (esExenta ? total : 0)
  const neto       = doc.neto ?? (esExenta ? 0 : (esBoleta ? total : Math.round(total / 1.19)))
  const iva        = doc.iva  ?? (esExenta ? 0 : (esBoleta ? 0 : total - Math.round(total / 1.19)))
  const items      = doc.items ?? [{ descripcion: doc.receptor, cant: 1, precioUnit: total, descuento: 0, valor: total }]

  const ctx = { doc, empresa, tipoLabel, colorDoc, esExenta, esBoleta, total, neto, netoExento, iva, items, logoBase64, logoAncho: logoAncho || 70 }
  return htmlCarta(ctx)  // siempre carta para email
}
