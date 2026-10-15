PROJECT      := aes-movie-player
DOCKER_IMAGE := $(PROJECT)-toolchain
DOCKER_USER  := $(shell id -u):$(shell id -g)
DOCKER_RUN   := docker run --rm --platform linux/amd64 --user $(DOCKER_USER) \
                -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE)
BUILD        := build
OBJECTS      := $(BUILD)/main.o $(BUILD)/menu.o $(BUILD)/fmv.o $(BUILD)/timeline.o

.PHONY: all image rom analyse timing hooks shell clean distclean
all: rom

image:
	docker build --platform linux/amd64 --provenance=false --target toolchain -t $(DOCKER_IMAGE) .

rom: image
	AESMOVIE_TOOLCHAIN_IMAGE=$(DOCKER_IMAGE) bash toolchain/build-in-docker.sh

analyse: image
	$(DOCKER_RUN) cppcheck --std=c99 --enable=warning,style,performance,portability \
	    --check-level=exhaustive --inline-suppr --error-exitcode=1 --quiet \
	    --suppress=missingInclude --suppress=missingIncludeSystem \
	    --suppress=unmatchedSuppression \
	    -Isrc -Isrc/fmv -Isrc/player src
	@echo "static analysis clean"

timing:
	uv --project tools run python tools/scripts/check_vram_timing.py $(OBJECTS)

hooks:
	git config core.hooksPath .githooks

shell: image
	docker run --rm -it --platform linux/amd64 --user $(DOCKER_USER) \
	    -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) bash

clean:
	rm -rf $(BUILD)

distclean: clean
	-docker rmi $(DOCKER_IMAGE)
