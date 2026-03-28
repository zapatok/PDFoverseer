# Plan Técnico y Arquitectónico: Inferencia Orgánica de Alineación Suave

## 1. Visión General y Motivación
El motor original de `master` destacaba por su robustez al delegar la inferencia en propagaciones direccionales simples (Forward/Backward) y un acoplamiento flojo con la información del periodo (Dempster-Shafer final). 

La reciente iteración (`feature/inference-engine`) introdujo heurísticas "frágiles" y agresivas (fusión forzada PDM, sustitución forzada MP, algoritmo constreñido Viterbi) que rompen con flexibilidad en distribuciones reales de documentos. 

Este plan propone una **Arquitectura de Inferencia Orgánica Probabilística**, que expande el diseño original de `master` mediante **Alineación Suave de Secuencias (Soft Sequence Alignment)** y **Degradación de Confianza**, resolviendo los casos límite sin fijar reglas rígidas y evaluándolas algorítmicamente vía `eval sweeps`.

---

## 2. Arquitectura Matemática y Lógica

La nueva canalización dentro de `_infer_missing` se estructurará en 4 subsistemas probabilísticos fluidos:

### 2.1 Subsistema 0: Degradación de Confianza OCR (Natural Anomaly Dropout)
En lugar de forzar parches como `_multi_period_correction` (que sobrescribía rachas de `total=1`), el motor debe **dudar algorítmicamente** de sus "certezas" OCR si estas rompen la inercia sin sentido.
* **Técnica:** Sobre el array de `reads`, calcular un "Índice de Anomalía" iterativo para cada página leída directamente por OCR (`direct` o `SR`) cuya `confidence` original no sea del 100%.
* **Flujo Computacional:** 
  1. Si la lectura OCR local exige un salto de documento injustificado respecto a la inercia (ej. página 1 de 4, luego página 1 de 1, luego 3 de 4).
  2. Ajustar `read.confidence -= anomaly_penalty`.
  3. Si `read.confidence < anomaly_dropout_threshold`, transmutar su `method` a `"failed"`. No intentamos "adivinar" el valor real aquí; dejamos que el resto del canal de inferencia reconstruya ese hueco de forma natural.

### 2.2 Subsistema 1 y 2: Proyecciones Bidireccionales Espejadas (Forward & Backward)
A diferencia del `master` primitivo (que ejecutaba Forward y luego rellenaba los huecos sobrantes con Backward, generando choques en el centro de grandes vacíos de lectura), proponemos proyecciones independientes y simuladas.
* **Técnica:** 
  1. Clonar el estado de los fallos.
  2. Correr la propagación `Forward` pura desde las anclas OCR certeras de izquierda a derecha de forma algorítmica y guardar el resultado temporal (`reads_fwd_hyp`).
  3. Correr la propagación `Backward` pura desde las anclas OCR de derecha a izquierda y guardar el resultado temporal (`reads_bwd_hyp`).

### 2.3 Subsistema 3: Resolución Suave de Conflictos (Soft Clash Resolution)
Punto neurálgico del framework donde se evalúan discrepancias.
* **Técnica:** Para cada índice `i` donde `reads_fwd_hyp[i]` difiera lógicamente de `reads_bwd_hyp[i]` (ej. cruce en secuencias ruidosas de 10 páginas fallidas consecuentemente), crear secuencias candidatas y someterlas a una *Función de Costo*.
* **Función de Costo Híbrida (Objective Function):**
  Definimos el "Costo de Anomalía" `C(S)` de una secuencia hipotética `S` como la combinación lineal:
  `C(S) = (W1 * Distancia_Local) + (W2 * Distancia_Periodo) + (W3 * Penalidad_Continuidad_Hipotética)`
  * `Distancia_Local`: Discrepancia con `_local_total` (inercia a corto plazo).
  * `Distancia_Periodo`: Penalidad si la secuencia no respeta los límites asintóticos indicados por `period_info` (Autocorrelación/Alineación asintótica global).
  * *Selección:* Asignaremos a `reads[i]` los valores exactos definidos en la cadena `S` de menor costo.

---

## 3. Flujo de Control en Tubería (Data Flow)

Al eliminar las injerencias de Phase D, Phase MP y PDM, el flujo de procesamiento recobra compatibilidad pura para `core/analyzer.py` y `eval/inference.py`:

```mermaid
graph TD;
    A[Lecturas CRUDAS de OCR + Period Info] --> B[Downgrade: Anomalías OCR -> method='failed']
    B --> C{Ramas de Propagación Simuladas}
    C --> D[Simulación Forward completo]
    C --> E[Simulación Backward completo]
    D --> F[Punto de Encuentro/Clash]
    E --> F
    F --> G{¿Hay Conflicto de Índices?}
    G -- No --> H[Consolidar Valores Directamente]
    G -- Sí --> I[Calcular Función de Costo C_S]
    I --> J[Elegir Hipótesis Ganadora por Consolidación Local/Periodo]
    H --> K[Cross-Validation D-S post-inferencial (Master Original)]
    J --> K
    K --> L[Retorno de Reads Limpios y Cohesivos]
```

---

## 4. Diseño del Espacio de Parámetros de Evaluación (`eval sweeps`)

Para confirmar que esta arquitectura matemática es funcional y no "magia hardcodeada", someteremos el modelo a nuestra herramienta de barrido y benchmarking usando nuestra suite estandarizada en `eval/fixtures/real/` (que incluye las verdades de campo como `HLL.json`, `ART.json`, `CH_39.json`, etc.) y las pruebas unitarias en `eval/fixtures/synthetic/`.

Integraremos y afinaremos estadísticamente mediante `GridSearchCV` custom de la suite `eval`:
1. **`anomaly_dropout_threshold`**: (0.35 a 0.70). ¿Qué tanta presión estocástica necesita una lectura asimétrica del OCR para ser degradada a "fallo ciego"?
2. **`cost_weight_local` (W1)**: (0.1 a 1.0). Inercia vs Novedad.
3. **`cost_weight_period` (W2)**: (0.1 a 1.0). Cuan determinante es el patrón rítmico principal si un documento cambia sorpresivamente de longitud en la mitad del charco estadístico.
4. **`doc_boundary_probability_bias`**: (0.1 a 0.4). Al acabar un total (curr=total), ¿qué inclinación extra requiere un nuevo documento para formarse si el periodo local aconseja no cerrarlo?

---

## 5. Plan de Ejecución Iterativo (Step-by-Step)

**Iteración 1: Rollback Arquitectónico y Baseline Check**
* Eliminar Phase D (`_viterbi_anchor_constrained`, `_pick_doc_size`, `_apply_chain`, `_extract_anchors`).
* Eliminar Fase MP (`_multi_period_correction`).
* Eliminar PDM (`_period_doc_merge`).
* Correr testing actual contra nuestro set en la línea base libre de heurísticas estáticas. Recolectar deltas finales base (cuántos falsos positivos/negativos produce el motor desnudo sin forzamientos algorítmicos).

**Iteración 2: Implementación de Pases Espejos y Downgrade Suave**
* Refactorizar el motor de propagación de `_infer_missing` en eval y core para instanciar las ramas `reads_fwd_hyp` y `reads_bwd_hyp`. Modificar `PARAM_SPACE` de la suite de `eval` para acomodar los nuevos pesos de Costo de Anomalía.
* Programar el **Sub 0 (Anomaly Dropout)**. Validar empíricamente que rachas OCR corrompidas sean degradadas prolijamente en los reportes `--debug`.

**Iteración 3: Implementación del Motor de Resolución de Conflicto**
* Programar el discriminador algorítmico **Soft Clash** empleando la Función de Costo Híbrida. Sustituyendo a Phase X de manera orgánica y sin imposiciones rústicas de variables enteras.

**Iteración 4: Benchmarking Cruzado (Sweeps y Fine-tuning)**
* Ejecutar un Sweep comprensivo con las variables descubiertas arriba en el cluster en simultáneo. Seleccionar la combinación ganadora que repare de facto HLL, ART, INS y CH sin usar reglas absolutas o Viterbi duro.

**Iteración 5: Reintegración y Merge**
* Reemplazar parámetros de producción en `eval/params.py` y constantes duras de `core/analyzer.py`. Consolidación final del código y confirmación sin regresiones.
