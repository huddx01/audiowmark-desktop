PYTHON     := /opt/homebrew/bin/python3
SRC        := src/audiowmark_gui.py
APP_NAME   := Audiowmark Desktop
QT_PLUGINS := /opt/homebrew/Cellar/qtbase/6.11.0/share/qt/plugins

.PHONY: run bundle clean

run:
	$(PYTHON) $(SRC)

bundle:
	/opt/homebrew/bin/pyinstaller \
		--windowed \
		--onedir \
		--name "$(APP_NAME)" \
		--icon img/AppIcon.icns \
		--add-binary "$(QT_PLUGINS)/platforms/libqcocoa.dylib:PyQt6/Qt6/plugins/platforms/" \
		--add-binary "$(QT_PLUGINS)/styles/libqmacstyle.dylib:PyQt6/Qt6/plugins/styles/" \
		--add-binary "/usr/local/bin/audiowmark:." \
		-y \
		$(SRC)
	@echo "Bundle created in dist/"

clean:
	rm -rf build dist *.spec __pycache__ src/__pycache__
