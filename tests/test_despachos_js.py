import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ambulancias_pergamino.mapa import exportar_mapa


class DespachosJavascriptTest(unittest.TestCase):
    def test_despachos_multiples_liberacion_hospital_y_pacientes(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Se necesita Node.js para las pruebas de despacho')
        raiz = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / 'mapa.html'
            exportar_mapa(raiz / 'data/pergamino.json', raiz / 'config/ambulancias.json', html)
            codigo = re.findall(r'<script>(.*?)</script>', html.read_text(encoding='utf-8'), re.S)[0]
            bloque = codigo[codigo.index('    const botonAsignar ='):codigo.index('    const formularioUrgencia =')]
            arnes = r'''
const assert = require('node:assert/strict');
const controles = {};
function control(id) { return controles[id] ||= {value:'', options:[], addEventListener(event, fn){this[event]=fn}}; }
const document = {getElementById:control};
const selectorAmbulancia = control('ambulancia');
const selectorEmergencia = control('emergencia');
const selectorEstablecimiento = control('establecimiento');
const datos = {emergencias:[{id:'E1', cantidad_pacientes:2, ambulancias_requeridas:2}], ambulancias:[], rutas:{}};
const ambulanciasPorId = {A1:{capacidad_pacientes:1}, A2:{capacidad_pacientes:1}};
const establecimientosPorId = {};
const alternativasPorClave = {};
for (const a of ['A1','A2']) for (const e of ['GUARDIA-1','GUARDIA-2']) {
 alternativasPorClave[`${a}|E1|${e}`] = {ambulancia_id:a, emergencia_id:'E1', establecimiento_id:e, distancia_total_m:100, es_factible:true};
}
function setInterval() {}
function dibujarAlternativa() {}
function nombreDeAmbulancia(id) { return id; }
function Option(text, value) { this.text=text; this.value=value; }
selectorEmergencia.add = opcion => selectorEmergencia.options.push(opcion);
Object.defineProperty(selectorEmergencia, 'length', {
 set(value) { selectorEmergencia.options.length=value; }
});
''';
            casos = r'''
renderDashboard = () => {};
prepararSiguienteDespacho = () => {};
refrescarSelectores = () => {};
hospitalDisponible.value='si'; pacientesDespacho.value='1';
function asignar(a, destino='GUARDIA-1') {
 selectorAmbulancia.value=a; selectorEmergencia.value='E1'; selectorEstablecimiento.value=destino; botonAsignar.click();
}
asignar('A1','GUARDIA-2'); assert.equal(despachos.size,0);
pacientesDespacho.value='2'; asignar('A1'); assert.equal(despachos.size,0);
pacientesDespacho.value='-1'; asignar('A1'); assert.equal(despachos.size,0);
pacientesDespacho.value='0.5'; asignar('A1'); assert.equal(despachos.size,0);
pacientesDespacho.value='1';
asignar('A1'); assert.equal(despachos.size,1); assert.equal(coberturaCompleta('E1'),false);
refrescarSelectorEmergencias();
assert.equal(selectorEmergencia.options.some(o => o.value === 'E1'), true, 'La cobertura parcial sigue seleccionable');
asignar('A2'); assert.equal(despachos.size,2); assert.equal(coberturaCompleta('E1'),true);
refrescarSelectorEmergencias();
assert.equal(selectorEmergencia.options.some(o => o.value === 'E1'), false, 'La cobertura completa sale del selector');
assert.equal(selectorEmergencia.value, '', 'La selección anterior debe limpiarse');
asignar('A1'); assert.equal(despachos.size,2);
hospitalDisponible.value='no';
assert.equal(despachos.size,2); // Cambiar hospital conserva servicios en curso.
dashboardLista.click({target:{closest:()=>({getAttribute:()=> 'A1'})}});
assert.equal(despachos.size,1); assert.equal(despachos.has('A2'),true);
assert.equal(atendidas.size,1);
despachos.get('A2').liberacionEn=Date.now()-1;
liberarVencidos(); assert.equal(despachos.size,0); assert.equal(atendidas.size,2);
assert.equal(coberturaCompleta('E1'),true);
datos.emergencias.push({id:'E2',cantidad_pacientes:1,ambulancias_requeridas:1});
assert.equal(destinoPermitido({establecimiento_id:'GUARDIA-1'}),false);
assert.equal(destinoPermitido({establecimiento_id:'GUARDIA-2'}),true);
'''
            js = Path(d) / 'prueba.js'
            js.write_text(arnes + bloque + casos, encoding='utf-8')
            r = subprocess.run([node, str(js)], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(0, r.returncode, r.stderr)
