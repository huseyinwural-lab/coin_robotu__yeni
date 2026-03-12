def build_correlation_clusters(matrix_payload: dict, *, threshold: float = 0.75) -> dict:
    symbols = list(matrix_payload.get("symbols") or [])
    matrix = matrix_payload.get("correlation_matrix") or {}

    neighbors: dict[str, set[str]] = {symbol: set() for symbol in symbols}
    for base in symbols:
        for compare in symbols:
            if base == compare:
                continue
            corr = float((matrix.get(base) or {}).get(compare) or 0.0)
            if corr >= threshold:
                neighbors[base].add(compare)

    clusters: list[dict] = []
    visited: set[str] = set()

    for symbol in symbols:
        if symbol in visited:
            continue

        stack = [symbol]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            for nxt in sorted(neighbors.get(current, set())):
                if nxt not in component:
                    stack.append(nxt)

        ordered_symbols = sorted(component)
        for item in ordered_symbols:
            visited.add(item)

        avg_corr = 1.0
        pair_count = 0
        pair_sum = 0.0
        for idx, base in enumerate(ordered_symbols):
            for compare in ordered_symbols[idx + 1 :]:
                pair_sum += float((matrix.get(base) or {}).get(compare) or 0.0)
                pair_count += 1
        if pair_count > 0:
            avg_corr = round(pair_sum / pair_count, 4)

        clusters.append(
            {
                "cluster_id": f"CLUSTER_{len(clusters) + 1}",
                "symbols": ordered_symbols,
                "avg_correlation": avg_corr,
                "size": len(ordered_symbols),
            }
        )

    return {
        "threshold": threshold,
        "correlation_clusters": clusters,
    }
