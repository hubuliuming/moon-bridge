package anthropic

import (
	"encoding/json"
)

func sanitizeEmptyNameTools(body []byte) []byte {
	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		return body
	}

	rawTools, ok := payload["tools"].([]any)
	if !ok {
		return body
	}

	filtered := make([]any, 0, len(rawTools))
	changed := false

	for _, item := range rawTools {
		tool, ok := item.(map[string]any)
		if !ok {
			filtered = append(filtered, item)
			continue
		}

		// Anthropic-style tool:
		// { "name": "", "input_schema": {...} }
		if name, exists := tool["name"]; exists {
			if s, ok := name.(string); ok && s == "" {
				changed = true
				continue
			}
		}

		// OpenAI-style function tool:
		// { "type": "function", "function": { "name": "" } }
		if fn, ok := tool["function"].(map[string]any); ok {
			if name, exists := fn["name"]; exists {
				if s, ok := name.(string); ok && s == "" {
					changed = true
					continue
				}
			}
		}

		filtered = append(filtered, item)
	}

	if !changed {
		return body
	}

	payload["tools"] = filtered

	newBody, err := json.Marshal(payload)
	if err != nil {
		return body
	}

	return newBody
}