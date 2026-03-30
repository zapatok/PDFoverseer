# Análisis de Segmentación Visual (feature/pixel-density)

Este documento resume los hallazgos y conclusiones de la fase experimental de "Pixel Density", orientada a encontrar una heurística puramente matemática/espacial veloz para segmentar presentaciones masivas en un archivo PDF unificado.

## Objetivos del Experimento
El objetivo central era detectar las "portadas" (diapositivas de inicio) de los diferentes documentos o expositores dentro de un PDF concatenado, renderizando las páginas a baja resolución (50 DPI) y evaluando proporciones de píxeles oscuros vs blancos, sin recurrir a procesamiento NLP o lectura OCR costosa.

## Modelos Algorítmicos Desarrollados

Se implementaron cinco estrategias progresivas en Python usando NumPy, PyMuPDF y Scikit-Learn:

1. **Scalar (Global Ratio):** 
   - *Metodología:* Mide el porcentaje total de tinta negra en toda la página.
   - *Falla:* Diferentes portadas tienen fondos distintos (textos negros en fondo blanco = ratio mínimo, vs gráficas en fondo oscuro = ratio máximo). Totalmente inconsistente.

2. **Grid ($N \times N$ Tile Vectors):** 
   - *Metodología:* Divide la página en una cuadrícula (ej. 4x4) generando un vector espacial de 16 dimensiones. Compara distancias Euclidianas (L2) contra páginas de referencia.
   - *Mejora:* Reconoce la "ubicación" del texto (ej. título siempre al centro), ignorando logos o márgenes blancos. Es la base de todos los experimentos exitosos.

3. **Ref-Spread (Patrones Asimétricos):** 
   - *Metodología:* Toma $N$ páginas que sabemos que son portadas, mide su dispersión L2 (cuánto difieren entre sí), y crea una "banda de tolerancia paramétrica".
   - *Falla:* Las presentaciones tienen "ruido" interno. Una diapositiva en blanco en medio de una charla (ej. pausa o gráfico simple) puede verse idéntica a una portada simple. Falsos positivos.

4. **Break-Mode (Detección de Saltos Temporales):** 
   - *Metodología:* Abandona el absolutismo. Mide la magnitud del cambio espacial (salto L2) solo entre la página **N** y la página **N+1**. Una portada nueva siempre rompe el molde de la diapositiva final anterior.
   - *Falla:* Falsos positivos endémicos. Pasar de una tabla diminuta a un gráfico a pantalla completa en la misma charla genera un "salto temporal" igual o superior al de cambiar de expositor.

5. **Hybrid Delta Clustering (Break + Clustering):** 
   - *Metodología:* Calcula todos los "Saltos L2 temporales" (Deltas) del PDF completo. Luego, usa `K-Means (k=2)` para separar los saltos normales de la charla, respecto a los "saltos extraordinarios".
   - *Falla Final empírica:* Funciona impecable en PDFs pequeños, pero en PDFs gigantes, K-Means corta el clúster a partir de ~0.24, y aún así encuentra >1000Matches. Hay "ruido temporal" brutal provocado por las visuales complejas de los presentadores.

## Resultados Clave (DPI: 50 | Grid: 4x4 | Hybrid Delta Clustering)

| Archivo PDF | Target (Portadas Reales) | Matches (Portadas Matemáticas) | Análisis |
|---|---|---|---|
| **HLL_363docs.pdf** | 363 | 373 | Segmentación impecable, ~97% efectividad. Umbral estadístico: `0.11`. |
| **ART_HLL_674docsapp.pdf** | 674 | 1075 | Sobre-segmentación grosera. Umbral estadístico: `0.26`. |

## La Conclusión: Imposibilidad Espacial

El experimento demostró empírica y matemáticamente que **la segmentación puramente técnica-visual toca un techo**. 
Para un algoritmo agnóstico, el salto visual entre la "última slide de conclusiones" y la "nueva portada corporativa" es matemáticamente *menor* que el salto visual de "una diapositiva de texto a un diseño infográfico disruptivo del mismo autor".

A simple vista un humano distingue la portada (por semántica gráfica), pero los píxeles no diferencian semántica.

## Propuesta Definitiva: El Filtro Híbrido OCR

La infraestructura algorítmica veloz de `pixel_density.py` no debe descartarse, sino utilizarse como un **Pre-Filtro (Rastreador de Candidatos):**

1. Corremos el PDF en `pixel_density.py` (Hybrid Break Mode) a 50 DPI. Toma ~4 segundos generar la lista de posibles portadas.
2. Agarraremos todos esos saltos visuales fuertes (Ej. los 1075 falsos documentados).
3. En vez de escanear (OCR) un PDF crudo de 2700 páginas a costo altísimo, le entregamos al motor de Reconocimiento de Datos Estructurados solamente ese 30% del documento (las 1075 páginas sospechosas).
4. El OCR las lee y aplica su lógica de negocio o LLM: *"¿Esta página dice palabras clave típicas (Presents, Nombre del relator, Título corporativo, ID de póster)?"*

Bajar los candidatos de `2719` a `1075` antes de usar IA o Tesseract multiplicará el rendimiento por ~300% abaratando tiempo informático, asegurando al mismo tiempo que filtramos falsos positivos y resolvemos el problema final.
