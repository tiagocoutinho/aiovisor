main = {
    "base": "/hello",
    "directory": "{main[base]}/world"
}

program = {
    "web-server-lab1": {
        "command": "{main[base]}/exec something",
        "groups": ["web", "lab1"],
        "priority": 9
    }
}

