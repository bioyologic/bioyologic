import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/format.dart';
import 'result_screen.dart';

/// Datos de la muestra tras hacer/elegir la foto, y envío al servidor.
class NewAnalysisScreen extends StatefulWidget {
  const NewAnalysisScreen({
    super.key,
    required this.image,
    required this.filename,
    this.plateFraction,
    this.fromCamera = false,
    this.projectId,
  });

  final Uint8List image;
  final String filename;
  final double? plateFraction;
  final bool fromCamera;
  final int? projectId;

  @override
  State<NewAnalysisScreen> createState() => _NewAnalysisScreenState();
}

class _NewAnalysisScreenState extends State<NewAnalysisScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _volume = TextEditingController();
  List<Project> _projects = [];
  int? _projectId;
  int? _dilutionExp = 4;
  bool _plateFillsPhoto = true;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _projectId = widget.projectId;
    final state = AppScope.read(context);
    _volume.text = fmt(state.defaultVolumeMl, 2);
    state.api.projects().then((p) {
      if (mounted) setState(() => _projects = p);
    }).catchError((_) {});
    state.api.stats().then((s) {
      if (mounted && _name.text.isEmpty) _name.text = 'Caja #${s.analyses + 1}';
    }).catchError((_) {});
  }

  @override
  void dispose() {
    _name.dispose();
    _volume.dispose();
    super.dispose();
  }

  double? get _volumeMl => double.tryParse(_volume.text.replaceAll(',', '.'));

  double? get _dilution {
    final e = _dilutionExp;
    if (e == null) return null;
    var d = 1.0;
    for (var i = 0; i < e; i++) {
      d /= 10;
    }
    return d;
  }

  Future<void> _analyze() async {
    if (!_form.currentState!.validate()) return;
    final state = AppScope.read(context);
    setState(() => _busy = true);
    try {
      // Foto de galería: si la placa llena la foto, su diámetro ≈ 95 % del lado corto.
      final fraction = widget.plateFraction ?? (_plateFillsPhoto ? 0.95 : null);
      final a = await state.api.createAnalysis(
        image: widget.image,
        filename: widget.filename,
        sampleName: _name.text.trim(),
        projectId: _projectId,
        dilution: _dilution,
        volumeMl: _dilution == null ? null : _volumeMl,
        plateFraction: fraction,
        plateDiameterMm: state.plateDiameterMm,
      );
      state.dataChanged();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(analysisId: a.id)));
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        showSnack(context, e.message);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Stack(children: [
      Scaffold(
        appBar: AppBar(title: const Text('Nueva muestra')),
        body: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: AspectRatio(
                  aspectRatio: 1.4,
                  child: Container(color: Colors.black, child: Image.memory(widget.image, fit: BoxFit.contain)),
                ),
              ),
              const SizedBox(height: 20),
              TextFormField(
                controller: _name,
                decoration: const InputDecoration(labelText: 'Nombre de la muestra', prefixIcon: Icon(Icons.label_outline)),
                validator: (v) => (v == null || v.trim().isEmpty) ? 'Obligatorio' : null,
              ),
              const SizedBox(height: 14),
              DropdownButtonFormField<int?>(
                initialValue: _projectId,
                decoration: const InputDecoration(labelText: 'Proyecto', prefixIcon: Icon(Icons.folder_outlined)),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Sin proyecto')),
                  for (final p in _projects) DropdownMenuItem(value: p.id, child: Text(p.name)),
                  if (_projectId != null && _projects.every((p) => p.id != _projectId))
                    DropdownMenuItem(value: _projectId, child: const Text('Proyecto actual')),
                ],
                onChanged: (v) => setState(() => _projectId = v),
              ),
              const SizedBox(height: 22),
              const Text('Siembra', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text('Necesaria para calcular las UFC/mL.', style: TextStyle(color: muted, fontSize: 13)),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: DropdownButtonFormField<int?>(
                    initialValue: _dilutionExp,
                    decoration: const InputDecoration(labelText: 'Dilución'),
                    items: [
                      const DropdownMenuItem(value: null, child: Text('No indicar')),
                      for (var e = 0; e <= 9; e++)
                        DropdownMenuItem(value: e, child: Text(e == 0 ? 'Sin diluir' : '10${superscript(-e)}')),
                    ],
                    onChanged: (v) => setState(() => _dilutionExp = v),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    controller: _volume,
                    enabled: _dilutionExp != null,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(labelText: 'Volumen', suffixText: 'mL'),
                    validator: (_) {
                      if (_dilutionExp == null) return null;
                      final v = _volumeMl;
                      return (v == null || v <= 0) ? 'Mayor que 0' : null;
                    },
                  ),
                ),
              ]),
              if (!widget.fromCamera) ...[
                const SizedBox(height: 12),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _plateFillsPhoto,
                  onChanged: (v) => setState(() => _plateFillsPhoto = v),
                  title: const Text('La placa ocupa toda la foto'),
                  subtitle: Text('Permite medir las colonias en milímetros. Si no, se mostrarán en píxeles.',
                      style: TextStyle(color: muted, fontSize: 12.5)),
                ),
              ],
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _busy ? null : _analyze,
                icon: const Icon(Icons.biotech),
                label: const Text('Analizar placa'),
              ),
            ],
          ),
        ),
      ),
      if (_busy) const _AnalyzingOverlay(),
    ]);
  }
}

class _AnalyzingOverlay extends StatelessWidget {
  const _AnalyzingOverlay();

  @override
  Widget build(BuildContext context) => Material(
        color: Bio.green,
        child: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const SizedBox(width: 64, height: 64, child: CircularProgressIndicator(color: Bio.mint, strokeWidth: 3)),
            const SizedBox(height: 24),
            const Text('Analizando la placa…',
                style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Text('Detectando y midiendo colonias',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.75))),
          ]),
        ),
      );
}
