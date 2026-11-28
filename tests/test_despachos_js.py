import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ambulancias_pergamino.mapa import exportar_mapa


class DespachosJavascriptTest(unittest.TestCase):
    def test_despachos_multiples_destino_elegido_y_pacientes_automaticos(self):
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
const datos = {emergencias:[{id:'E1', cantidad_pacientes:2, ambulancias_requeridas:1}], ambulancias:[], rutas:{}};
const ambulanciasPorId = {A1:{capacidad_pacientes:2}, A2:{capacidad_pacientes:2}};
const establecimientosPorId = {};
const alternativasPorClave = {};
for (const a of ['A1','A2']) for (const e of ['E1','E2']) for (const d of ['GUARDIA-1','GUARDIA-2']) {
 alternativasPorClave[`${a}|${e}|${d}`] = {ambulancia_id:a, emergencia_id:e, establecimiento_id:d, distancia_total_m:100, distancia_ambulancia_emergencia_m:50, distancia_emergencia_establecimiento_m:50, es_factible:true};
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
function asignar(a, emergencia='E1', destino='GUARDIA-1') {
 selectorAmbulancia.value=a; selectorEmergencia.value=emergencia; selectorEstablecimiento.value=destino; botonAsignar.click();
}
asignar('A1','E1','GUARDIA-2');
assert.equal(despachos.size,1, 'El operador puede elegir la clínica como destino');
assert.equal(despachos.get('A1').pacientes,1, 'Cada unidad traslada un paciente aunque tenga capacidad mayor');
assert.ok(despachos.get('A1').inicioEn, 'La fase del despacho arranca al asignar la unidad');
assert.equal(coberturaCompleta('E1'),false);
refrescarSelectorEmergencias();
assert.equal(selectorEmergencia.options.some(o => o.value === 'E1'), true, 'La urgencia con pacientes pendientes sigue seleccionable');
asignar('A2');
assert.equal(despachos.size,2); assert.equal(despachos.get('A2').pacientes,1);
assert.equal(coberturaCompleta('E1'),true);
refrescarSelectorEmergencias();
assert.equal(selectorEmergencia.options.some(o => o.value === 'E1'), false, 'La cobertura completa sale del selector');
assert.equal(selectorEmergencia.value, '', 'La selección anterior debe limpiarse');
asignar('A1'); assert.equal(despachos.size,2);
dashboardLista.click({target:{closest:()=>({getAttribute:()=> 'A1'})}});
assert.equal(despachos.size,1); assert.equal(despachos.has('A2'),true);
assert.equal(atendidas.size,1);
despachos.get('A2').liberacionEn=Date.now()-1;
liberarVencidos(); assert.equal(despachos.size,0); assert.equal(atendidas.size,2);
assert.equal(coberturaCompleta('E1'),true);
datos.emergencias.push({id:'E2',cantidad_pacientes:1,ambulancias_requeridas:2});
asignar('A1','E2','GUARDIA-1');
assert.equal(despachos.get('A1').pacientes,1);
asignar('A2','E2','GUARDIA-2');
assert.equal(despachos.get('A2').pacientes,0, 'El refuerzo sin pacientes queda como apoyo');
assert.equal(coberturaCompleta('E2'),true);
'''
            js = Path(d) / 'prueba.js'
            js.write_text(arnes + bloque + casos, encoding='utf-8')
            r = subprocess.run([node, str(js)], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(0, r.returncode, r.stderr)

    def test_fases_del_despacho_por_trayectoria(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Se necesita Node.js para las pruebas de fase')
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
const selectorAmbulancia = control('a');
const selectorEmergencia = control('e');
const selectorEstablecimiento = control('d');
const datos = {emergencias:[], ambulancias:[], rutas:{}};
const ambulanciasPorId = {};
const establecimientosPorId = {};
const alternativasPorClave = {};
function setInterval() {}
function dibujarAlternativa() {}
function nombreDeAmbulancia(id) { return id; }
function Option(text, value) { this.text=text; this.value=value; }
'''
            casos = r'''
function fasePara(minutos) {
 const item = {
  inicioEn: Date.now() - minutos * 60000,
  liberacionEn: Date.now() + 60000,
  alternativa: {
   distancia_ambulancia_emergencia_m: 1000,
   distancia_emergencia_establecimiento_m: 1000
  }
 };
 return faseDespacho(item);
}
assert.equal(fasePara(0.5).texto, 'En camino al accidente');
assert.equal(fasePara(0.5).clase, 'fase-camino-accidente');
assert.equal(fasePara(2).texto, 'En escena');
assert.equal(fasePara(2).clase, 'fase-escena');
assert.equal(fasePara(12).texto, 'Camino al hospital');
assert.equal(fasePara(12).clase, 'fase-camino-hospital');
assert.equal(fasePara(14).texto, 'Regresando a la base');
assert.equal(fasePara(14).clase, 'fase-regreso');
'''
            js = Path(d) / 'fases.js'
            js.write_text(arnes + bloque + casos, encoding='utf-8')
            r = subprocess.run([node, str(js)], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(0, r.returncode, r.stderr)
