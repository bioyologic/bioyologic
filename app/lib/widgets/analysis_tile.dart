import 'package:flutter/material.dart';

import '../api/models.dart';
import '../screens/result_screen.dart';
import 'common.dart';
import 'format.dart';

/// Fila de un análisis en "Últimos análisis" / historial.
class AnalysisTile extends StatelessWidget {
  const AnalysisTile(this.a, {super.key});
  final Analysis a;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => ResultScreen(analysisId: a.id))),
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(children: [
            ApiImage(a.thumbUrl, width: 58, height: 58),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(a.sampleName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                const SizedBox(height: 2),
                Text('${a.summary.total} colonias${a.projectName != null ? ' · ${a.projectName}' : ''}',
                    maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: muted, fontSize: 13)),
                const SizedBox(height: 2),
                Text(friendlyDate(a.createdAt), style: TextStyle(color: muted, fontSize: 12)),
              ]),
            ),
            StatusChip(a.summary.status),
          ]),
        ),
      ),
    );
  }
}
