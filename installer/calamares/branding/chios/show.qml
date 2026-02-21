/* chiOS installer — installation slideshow */
import QtQuick 2.15

Rectangle {
    color: "#0c0b14"
    anchors.fill: parent

    Column {
        anchors.centerIn: parent
        spacing: 24

        Text {
            text: "✦"
            color: "#7c6af7"
            font.pixelSize: 64
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: "chiOS"
            color: "#e8e8f0"
            font.pixelSize: 42
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: "Your AI-native OS"
            color: "#9d90fa"
            font.pixelSize: 18
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Rectangle {
            width: 200
            height: 1
            color: "#2a2040"
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 12

            Repeater {
                model: [
                    "✦  Ask chi anything — just type or speak",
                    "✦  Local AI via Ollama — fully private",
                    "✦  Conversation history with data viewer",
                    "✦  Minimal, mouse-friendly desktop shell"
                ]
                delegate: Text {
                    text: modelData
                    color: "#c0c0d0"
                    font.pixelSize: 15
                    anchors.horizontalCenter: parent.horizontalCenter
                }
            }
        }
    }

    Text {
        text: "Installing chiOS — please wait…"
        color: "#7c6af7"
        font.pixelSize: 13
        font.italic: true
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 32
    }
}
