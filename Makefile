PROJECT      := neogeo-media-player
DOCKER_IMAGE := $(PROJECT)-toolchain
DOCKER_USER  := $(shell id -u):$(shell id -g)
DOCKER       := docker run --rm --platform linux/amd64 --user $(DOCKER_USER) \
                -e HOME=/tmp -v "$(CURDIR):/work" -w /work
DOCKER_RUN   := $(DOCKER) $(DOCKER_IMAGE)
BUILD        := build
EXAMPLE      := $(BUILD)/example
FMV_AUDIO    := no
OBJECTS      := $(BUILD)/main.o $(BUILD)/menu.o $(BUILD)/fmv.o $(BUILD)/timeline.o \
                $(BUILD)/fmv_audio.o $(BUILD)/guard.o

.PHONY: all image rom analyse timing cutscene hooks shell clean distclean
all: rom

image:
	docker build --platform linux/amd64 --provenance=false --target toolchain -t $(DOCKER_IMAGE) .

rom: image
	NEOGEOMEDIA_TOOLCHAIN_IMAGE=$(DOCKER_IMAGE) bash toolchain/build-in-docker.sh

analyse: image
	$(DOCKER_RUN) cppcheck --std=c99 --enable=warning,style,performance,portability \
	    --check-level=exhaustive --inline-suppr --error-exitcode=1 --quiet \
	    --suppress=missingInclude --suppress=missingIncludeSystem \
	    --suppress=unmatchedSuppression \
	    -Isrc -Isrc/fmv -Isrc/player src
	@echo "static analysis clean"

timing: image
	$(DOCKER_RUN) bash -c 'for object in $(OBJECTS); do \
	    m68k-neogeo-elf-objdump -dr "$$object" > "$$object.dis"; done'
	uv --project tools run python tools/scripts/check_vram_timing.py $(OBJECTS:.o=.o.dis)

cutscene: image
	$(DOCKER) -e BUNDLE=/work/$(BUILD)/bundle -e WORK=/work/$(EXAMPLE) \
	    -e FMV_AUDIO=$(FMV_AUDIO) $(DOCKER_IMAGE) bash examples/cutscene/build.sh

hooks:
	git config core.hooksPath .githooks

shell: image
	docker run --rm -it --platform linux/amd64 --user $(DOCKER_USER) \
	    -v "$(CURDIR):/work" -w /work $(DOCKER_IMAGE) bash

clean:
	rm -rf $(BUILD)

distclean: clean
	-docker rmi $(DOCKER_IMAGE)
