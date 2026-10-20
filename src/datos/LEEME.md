# Datos (Sebastián)

Esta carpeta tiene todo lo de la parte de datos: leer los archivos que nos dio Clarios, limpiarlos y dejar tablas listas para que Joshua haga los modelos y Gabriel el dashboard.

## Cómo correrlo

```bash
python src/datos/ejecutar_todo.py
```

Tarda menos de un minuto. Vuelve a hacer todas las tablas de `data/clean/`, las figuras y el informe de calidad, y revisa que todo cuadre. Al final tiene que decir **APTO**. Siempre salen 4 avisos de producción negativa (son reversos del ERP, ya los conocemos).

Otros comandos:

```bash
python tools/verificar_datos.py          # que los archivos de data/raw no hayan cambiado
python tools/validar_contrato.py         # solo la revisión de las tablas
python -m unittest discover -s tests     # las pruebas (unos 2 minutos)
python tools/generar_diccionario.py      # rehace docs/12 y docs/13
python tools/generar_informe_calidad.py  # rehace docs/14
```

## Qué hace cada script

| Script | Qué hace |
|---|---|
| `01_energia_scada.py` | Pasa los contadores de energía de RC a kWh por hora y por turno |
| `05_energia_fa.py` | Lo mismo para los 3 rectificadores de F&A |
| `02_produccion_erp.py` | Producción del ERP por turno y línea |
| `08_base_mensual.py` | Series mensuales de las 4 plantas, tarifa y metas de Clarios |
| `03_dataset_modelo.py` | Junta energía y producción por turno, día y semana (la tabla de Joshua) |
| `06_gas.py` | Gas diario de refinación |
| `04_eda_rc.py`, `07_eda_fa_gas.py` | Los análisis exploratorios y sus figuras |
| `energia_comun.py` | Funciones que usan los scripts de energía |

## Lo que hay que tener presente

- **Los contadores son acumulados.** Para sacar el consumo se restan lecturas, y para eso hay que arreglar reinicios, saltos y huecos.
- **El SCADA a veces se congela** (el mayor duró 586 horas, de julio a agosto de 2025). Esas horas se marcan como `estimado` y sirven para totales, no para analizar por turno.
- **Los turnos 6-14-22 son un supuesto**: Clarios no nos dio el calendario. Se cambian en `config/config.yaml`.
- **`operando` y el régimen se calculan con el mismo consumo**, así que no se usan para explicar el consumo.
- **Los 7 medidores de RC no son toda la planta**: frente a la base mensual de Clarios dan entre 0.49 y 1.24 (mediana 0.62). No se puede sacar un costo total de planta con ellos.
- **El gas solo tiene 2 meses** y no hay mes en común con la base de Clarios.
- Los detalles y las cifras con su estado están en `docs/04_supuestos_y_limitaciones.md` y `docs/11_cifras_verificadas.md`.

## Lo que falta

- Avisar a Joshua y Gabriel de los cambios en las tablas de F&A.
- Decidir con Joshua qué hacer con la semana del 13 de julio de F&A (probablemente está inflada).
- Atender lo que pidan Joshua y Gabriel.
- Elegir las cifras de la presentación y preparar mis láminas.
- La parte de datos está congelada con la etiqueta `v1.0` (13 de octubre; ver `docs/16_preparacion_v1.md`). Desde ahí solo se corrigen errores.

Clarios dijo que no va a mandar más datos, así que lo que no tenemos queda como supuesto o limitación y lo decimos claro.
